"""로컬 자료·도구 루프·평가·최종 저장을 연결하는 단일 분석 서비스입니다."""

import asyncio
import json
import logging
import re
import uuid
from time import monotonic

from app.address import resolve_site
from app.agentic.budget import RuntimeBudget
from app.agentic.preflight import collect_preflight
from app.agentic.questions import save_confirmed_space
from app.agentic.recording import CallRecording
from app.agentic.runtime import DecisionLoop
from app.agentic.snapshot import persist_snapshot_scores
from app.clock import utc_now_iso
from app.concurrency import run_in_thread
from app.config import BACKEND_DIR
from app.db import repository
from app.db.connection import connect, initialize
from app.errors import AnalysisConflictError
from app.llm.session import with_client_session
from app.local_data.adapter import LocalAdapter
from app.local_data.persistence import persist_local
from app.local_data.provenance import validate_snapshot
from app.schemas import AgentError, AnalysisTask
from app.storage.raw import CaptureScope, capture_scope
from app.storage.scrub import env_secrets, scrub_text

logger = logging.getLogger(__name__)

# 주소 해석부터 채점까지의 상한입니다. 측정 모드는 모델 호출을 전부 기록하느라 느립니다.
COLLECT_TIMEOUT_SECONDS = 120
MEASURING_COLLECT_TIMEOUT_SECONDS = 600


async def _event(path, request_id, stage, event):
    try:
        await run_in_thread(
            lambda: repository.append_event(request_id, stage, event, {}, db_path=path)
        )
    except Exception as exc:
        logger.warning("진행 이벤트 저장 실패: %s", type(exc).__name__)


def _persist_outcome(path, request_id, outcome):
    with connect(path) as db:
        if outcome.status == "waiting_for_input":
            db.execute(
                "UPDATE analysis_requests SET status='waiting_for_input' WHERE request_id=?",
                (request_id,),
            )
        else:
            db.execute(
                "UPDATE analysis_requests SET "
                "status='completed',result_json=?,completed_at=? WHERE "
                "request_id=?",
                (outcome.result.model_dump_json(), utc_now_iso(), request_id),
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
        error = AgentError(code="AGENTIC_FAILED", message="새 판단 실행을 완료하지 못했습니다.")
        failed_at = utc_now_iso()
        with connect(path) as db:
            changed = db.execute(
                "UPDATE analysis_requests SET error_json=?,status='failed',completed_at=? "
                "WHERE request_id=? AND status IN ('pending','running','waiting_for_input')",
                (error.model_dump_json(), failed_at, request_id),
            )
            if changed.rowcount != 1:
                raise ValueError("종료할 수 있는 요청이 없습니다.")
            db.execute(
                "INSERT INTO decision_failures(request_id,failed_at,error_json,"
                "diagnostics_json) "
                "VALUES(?,?,?,?)",
                (
                    request_id,
                    failed_at,
                    error.model_dump_json(),
                    json.dumps(diagnostics, ensure_ascii=False),
                ),
            )

    await run_in_thread(save)


def _make_recorder(request_id, recording_path, measurement):
    """측정 모드이거나 기록 경로를 받았을 때만 모델 호출을 파일로 남깁니다."""
    if not (measurement or recording_path):
        return None
    return CallRecording(recording_path or BACKEND_DIR / "cache" / f"{request_id}-model-calls.json")


async def _resolve_and_save_site(path, request_id, address, radius_m, resolve):
    """주소를 좌표로 바꿔 저장하고, 이어지는 단계가 쓸 작업 단위를 돌려줍니다."""
    site = await (resolve or resolve_site)(address)
    task = AnalysisTask(request_id=request_id, site=site, radius_m=radius_m)
    await run_in_thread(lambda: repository.save_site(task, db_path=path))
    await _event(path, request_id, "address", "completed")
    await _event(path, request_id, "local_data", "started")
    return task


async def _collect_and_score(scope, task, adapter):
    """로컬 자료를 적재해 채점합니다. 목업은 자료 없이 점수만 남깁니다."""
    if adapter is None:
        await persist_snapshot_scores(task)
        return {}, None
    observations, shared = await collect_preflight(scope, task.site)
    data, _, _ = await run_in_thread(persist_local, task, scope, adapter, None, observations)
    return data, shared


async def _finish_loop(loop):
    """루프를 돌리고, 초안이 나오면 평가까지 거쳐 최종 결과로 만듭니다."""
    outcome = await loop.run()
    if outcome.status == "draft_available":
        outcome = await loop.review_and_finalize()
    return outcome


@with_client_session
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
    path = await run_in_thread(initialize, db_path)
    if not request_prepared:
        await run_in_thread(
            lambda: repository.create_request(request_id, address, radius_m=radius_m, db_path=path)
        )
    budget = RuntimeBudget(measurement=measurement)
    recorder = _make_recorder(request_id, recording_path, measurement)
    limit = MEASURING_COLLECT_TIMEOUT_SECONDS if measurement else COLLECT_TIMEOUT_SECONDS
    stage, started, timings = "수집", monotonic(), {}
    try:
        await run_in_thread(lambda: repository.mark_running(request_id, db_path=path))
        await _event(path, request_id, "address", "started")
        async with capture_scope(request_id, path) as scope:
            adapter = await run_in_thread(LocalAdapter, local_data_path) if not mock else None
            async with asyncio.timeout(limit):
                task = await _resolve_and_save_site(path, request_id, address, radius_m, resolve)
                timings[stage] = monotonic() - started
                stage, started = "조회·채점" if adapter is not None else "채점", monotonic()
                data, shared = await _collect_and_score(scope, task, adapter)
                confirmed = (
                    await run_in_thread(save_confirmed_space, scope, confirmed_space)
                    if confirmed_space
                    else None
                )
                await scope.finish()
                timings[stage] = monotonic() - started
            stage, started = "루프", monotonic()
            await _event(path, request_id, "local_data", "completed")
            loop = await DecisionLoop.create(
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


@with_client_session
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
    path = await run_in_thread(initialize, db_path)
    context = await run_in_thread(lambda: repository.get_resume_context(request_id, db_path=path))
    scope = CaptureScope(request_id, path, context.run_id, context.snapshot_id)
    try:
        resume_state = await DecisionLoop.validate_resume(scope, answers)
    except ValueError as exc:
        raise AnalysisConflictError(str(exc)) from None
    recorder = _make_recorder(request_id, recording_path, measurement)
    try:
        await run_in_thread(validate_snapshot, scope)
        loop = await DecisionLoop.resume(
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
