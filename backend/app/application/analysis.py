"""로컬 자료·도구 루프·평가·최종 저장을 연결하는 단일 분석 서비스입니다."""

import asyncio
import json
import logging
import re
import uuid
from time import monotonic

from app.application.errors import INTERRUPTED_MESSAGE, AnalysisConflictError
from app.application.local_snapshot import persist_local
from app.application.ports.decision import decision
from app.application.ports.llm import llm, with_llm_session
from app.application.ports.market import market
from app.application.ports.storage import storage
from app.application.snapshot import persist_snapshot_scores
from app.domain.schemas import AgentError, AnalysisTask
from app.infrastructure.clients.address import ADDRESS_INPUT_ERRORS, GeocodeError, resolve_site
from app.infrastructure.config import BACKEND_DIR
from app.infrastructure.mock import dependencies, generators
from app.shared.clock import utc_now_iso
from app.shared.concurrency import run_in_thread
from app.shared.scrub import env_secrets, scrub_text

logger = logging.getLogger(__name__)

# 주소 해석부터 채점까지의 상한입니다. 측정 모드는 모델 호출을 전부 기록하느라 느립니다.
COLLECT_TIMEOUT_SECONDS = 120
MEASURING_COLLECT_TIMEOUT_SECONDS = 600


FAILURE_MESSAGES = {
    "ADDRESS_FAILED": "주소를 확인하지 못했어요. 주소를 다시 확인한 뒤 분석해 주세요.",
    "AI_FAILED": "AI 분석이 끝나지 못했어요. 잠시 후 다시 분석해 주세요.",
    "DATA_TIMEOUT": (
        "주변 자료를 불러오는 데 시간이 너무 오래 걸렸어요. 잠시 후 다시 분석해 주세요."
    ),
    "DATA_FAILED": "주변 자료를 불러오지 못했어요. 잠시 후 다시 분석해 주세요.",
    "AGENTIC_FAILED": "분석을 끝까지 마치지 못했어요. 잠시 후 다시 분석해 주세요.",
}


def public_failure(exc: BaseException, stage: str) -> AgentError:
    if isinstance(exc, asyncio.CancelledError):
        return AgentError(code="INTERRUPTED", message=INTERRUPTED_MESSAGE)
    if isinstance(exc, GeocodeError) and exc.code in ADDRESS_INPUT_ERRORS:
        code = "ADDRESS_FAILED"
    elif stage == "루프":
        code = "AI_FAILED"
    elif isinstance(exc, TimeoutError):
        code = "DATA_TIMEOUT"
    elif stage in {"조회·채점", "채점"}:
        code = "DATA_FAILED"
    else:
        code = "AGENTIC_FAILED"
    return AgentError(code=code, message=FAILURE_MESSAGES[code])


async def _event(path, request_id, stage, event):
    try:
        await run_in_thread(
            lambda: storage().requests.append_event(request_id, stage, event, {}, db_path=path)
        )
    except Exception as exc:
        logger.warning("진행 이벤트 저장 실패: %s", type(exc).__name__)


def _persist_outcome(path, request_id, outcome):
    if outcome.status == "waiting_for_input":
        storage().requests.save_outcome(request_id, db_path=path)
    else:
        storage().requests.save_outcome(
            request_id,
            result_json=outcome.result.model_dump_json(),
            completed_at=utc_now_iso(),
            db_path=path,
        )


async def _failure(path, request_id, exc, stage, timings=None):
    secrets = env_secrets()

    def safe(value):
        text = re.sub(r"https?://[^\s<>\"']+", "[URL 생략]", scrub_text(str(value), secrets))
        return text[:1000]

    causes = []
    cause = exc.__cause__
    while cause is not None and len(causes) < 4:
        causes.append(
            {
                "exception_class": type(cause).__name__,
                "message": safe(cause),
                "error_code": safe(getattr(cause, "sqlite_errorname", type(cause).__name__)),
            }
        )
        cause = cause.__cause__
    provider = getattr(exc, "diagnostics", {})
    diagnostics = [
        {
            "exception_class": type(exc).__name__,
            "error_code": safe(
                getattr(exc, "code", None) or provider.get("provider_code") or type(exc).__name__
            ),
            "http_status": provider.get("http_status"),
            "message": safe(exc),
            "stage": stage,
            "causes": causes,
            "phase_seconds": timings or {},
        }
    ]
    logger.error("새 판단 실행 실패: %s", json.dumps(diagnostics, ensure_ascii=False))

    def save():
        error = public_failure(exc, stage)
        failed_at = utc_now_iso()
        storage().requests.record_failure(
            request_id,
            error_json=error.model_dump_json(),
            diagnostics_json=json.dumps(diagnostics, ensure_ascii=False),
            failed_at=failed_at,
            db_path=path,
        )

    await run_in_thread(save)


def _make_recorder(request_id, recording_path, measurement):
    """측정 모드이거나 기록 경로를 받았을 때만 모델 호출을 파일로 남깁니다."""
    if not (measurement or recording_path):
        return None
    return llm().recording(
        recording_path or BACKEND_DIR / "cache" / f"{request_id}-model-calls.json"
    )


async def _resolve_and_save_site(path, request_id, address, radius_m, resolve):
    """주소를 좌표로 바꿔 저장하고, 이어지는 단계가 쓸 작업 단위를 돌려줍니다."""
    site = await (resolve or resolve_site)(address)
    task = AnalysisTask(request_id=request_id, site=site, radius_m=radius_m)
    await run_in_thread(lambda: storage().requests.save_site(task, db_path=path))
    await _event(path, request_id, "address", "completed")
    await _event(path, request_id, "local_data", "started")
    return task


async def _collect_and_score(scope, task, adapter):
    """로컬 자료를 적재해 채점합니다. 목업은 자료 없이 점수만 남깁니다."""
    if adapter is None:
        await persist_snapshot_scores(task)
        return {}, None
    observations, shared = await decision().preflight(scope, task.site)
    data, _, _ = await run_in_thread(persist_local, task, scope, adapter, None, observations)
    return data, shared


async def _finish_loop(loop):
    """루프를 돌리고, 초안이 나오면 평가까지 거쳐 최종 결과로 만듭니다."""
    outcome = await loop.run()
    if outcome.status == "draft_available":
        outcome = await loop.review_and_finalize()
    return outcome


@with_llm_session
async def execute_agentic_analysis(
    address,
    *,
    radius_m=500,
    db_path=None,
    request_id=None,
    resolve=None,
    mock=False,
    generate=None,
    advisor_generate=None,
    evaluator_generate=None,
    local_data_path=None,
    measurement=False,
    recording_path=None,
    allow_questions=False,
    request_prepared=False,
    confirmed_space=None,
):
    request_id = request_id or uuid.uuid4().hex
    path = await run_in_thread(storage().initialize, db_path)
    if not request_prepared:
        await run_in_thread(
            lambda: storage().requests.create_request(
                request_id, address, radius_m=radius_m, db_path=path
            )
        )
    budget = decision().budget(measurement=measurement)
    recorder = _make_recorder(request_id, recording_path, measurement)
    limit = MEASURING_COLLECT_TIMEOUT_SECONDS if measurement else COLLECT_TIMEOUT_SECONDS
    stage, started, timings = "수집", monotonic(), {}
    try:
        await run_in_thread(lambda: storage().requests.mark_running(request_id, db_path=path))
        await _event(path, request_id, "address", "started")
        async with storage().capture(request_id, path) as scope:
            adapter = (
                await run_in_thread(market().local_data, local_data_path) if not mock else None
            )
            async with asyncio.timeout(limit):
                task = await _resolve_and_save_site(path, request_id, address, radius_m, resolve)
                timings[stage] = monotonic() - started
                stage, started = "조회·채점" if adapter is not None else "채점", monotonic()
                data, shared = await _collect_and_score(scope, task, adapter)
                confirmed = (
                    await run_in_thread(decision().confirm_space, scope, confirmed_space)
                    if confirmed_space
                    else None
                )
                await scope.finish()
                timings[stage] = monotonic() - started
            stage, started = "루프", monotonic()
            await _event(path, request_id, "local_data", "completed")
            loop = await decision().create(
                scope,
                task.site,
                generate=generate,
                advisor_generate=advisor_generate,
                evaluator_generate=evaluator_generate,
                budget=budget,
                recorder=recorder,
                allow_questions=allow_questions,
                confirmed_space=confirmed,
            )
            if shared is not None:
                loop.adopt_shared(shared)
            loop.state["limitations"].extend(data.get("limitations", []))
            # 같은 dict 를 넘겨, 아래에서 기록하는 '루프' 시간까지 실패 진단에 함께 남습니다.
            loop.state["phase_seconds"] = timings
            outcome = await _finish_loop(loop)
            timings[stage] = monotonic() - started
            await loop.save(outcome.status, outcome.result)
            await run_in_thread(_persist_outcome, path, request_id, outcome)
            return outcome
    except (Exception, asyncio.CancelledError) as exc:
        timings[stage] = monotonic() - started
        await _failure(path, request_id, exc, stage, timings)
        await _event(path, request_id, "final", "failed")
        raise


@with_llm_session
async def resume_agentic_analysis(
    request_id,
    answers,
    *,
    db_path=None,
    generate=None,
    advisor_generate=None,
    evaluator_generate=None,
    measurement=False,
    recording_path=None,
):
    path = await run_in_thread(storage().initialize, db_path)
    context = await run_in_thread(
        lambda: storage().requests.get_resume_context(request_id, db_path=path)
    )
    scope = storage().resume_scope(request_id, path, context.run_id, context.snapshot_id)
    try:
        resume_state = await decision().validate_resume(scope, answers)
    except ValueError as exc:
        raise AnalysisConflictError(str(exc)) from None
    recorder = _make_recorder(request_id, recording_path, measurement)
    try:
        await run_in_thread(storage().provenance.validate_snapshot, scope)
        loop = await decision().resume(
            scope,
            context.site,
            answers,
            generate=generate,
            advisor_generate=advisor_generate,
            evaluator_generate=evaluator_generate,
            measurement=measurement,
            recorder=recorder,
            resume_state=resume_state,
        )
        outcome = await _finish_loop(loop)
        await scope.finish()
        await run_in_thread(_persist_outcome, path, request_id, outcome)
        return outcome
    except AnalysisConflictError:
        raise
    except (Exception, asyncio.CancelledError) as exc:
        await _failure(path, request_id, exc, "루프")
        raise


def mock_run_options(*, ask):
    return dependencies(ask=ask)


def mock_resume_options():
    return generators()
