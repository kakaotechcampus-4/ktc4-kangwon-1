"""오케스트레이터 실행 중 검증된 결과를 SQLite에 저장합니다."""

import asyncio
import sqlite3
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from functools import partial
from pathlib import Path
from typing import Any, Literal, overload

from app.address import resolve_site
from app.agents.decision import agent as decision
from app.agents.decision.agent import GenerateDecision
from app.agents.orchestration.graph import RunHooks, run_graph
from app.agents.orchestration.supplement import OnSupplement, validate_tools
from app.agents.orchestration.tools import MapLookup, SupplementTool
from app.agents.orchestration.workflow import (
    AgentRegistry,
    build_react_agents,
)
from app.db import repository
from app.db.connection import initialize
from app.schemas import (
    AGENT_IDS,
    DEFAULT_RADIUS_M,
    AgentAnalysis,
    AgentError,
    AnalysisTask,
    AnswerSubmission,
    DecisionResult,
    MapLookupPlan,
    MapObservation,
    QuestionSnapshot,
    Site,
    SupplementEvent,
    WaitingForInput,
    validate_radius,
)
from app.services.settings import ExecutionSettings, validate_timeout


async def _settle[T](operation: Coroutine[Any, Any, T]) -> T:
    """DB 스레드는 강제 중단할 수 없어 쓰기 결말 확인 후 취소를 전달합니다."""
    task = asyncio.create_task(operation)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise


class AnalysisAlreadyRunningError(RuntimeError):
    """동일 답변으로 이미 실행 중인 요청입니다."""


class AnalysisAlreadyFailedError(RuntimeError):
    """이미 실패한 답변 실행은 자동 재시도하지 않습니다."""


async def resume_analysis(
    submission: AnswerSubmission,
    *,
    db_path: str | Path | None = None,
    generate: GenerateDecision | None = None,
    settings: ExecutionSettings | None = None,
    overall_timeout: float | None = None,
) -> DecisionResult:
    """답변을 한 번만 수락하고 저장된 분석으로 최종판단을 재개합니다."""
    submission = AnswerSubmission.model_validate(submission)
    settings = settings or ExecutionSettings.from_env()
    db_path = db_path if db_path is not None else settings.db_path
    if generate is None:
        settings.decision_llm.require_credentials()
        generate = partial(decision.generate_decision, settings=settings.decision_llm)
    elif not callable(generate):
        raise ValueError("최종판단 호출 함수가 필요합니다.")
    timeout = settings.overall_timeout if overall_timeout is None else overall_timeout
    validate_timeout(timeout)
    owned = False

    async def claim() -> None:
        nonlocal owned
        owned = await asyncio.to_thread(repository.claim_question_resume, submission, db_path=path)

    try:
        async with asyncio.timeout(timeout):
            path = await _settle(asyncio.to_thread(initialize, db_path))
            await _settle(claim())
            if not owned:
                row = await asyncio.to_thread(
                    repository.get_request, submission.request_id, db_path=path
                )
                if row and row["status"] == "completed":
                    return DecisionResult.model_validate_json(row["result_json"])
                if row and row["status"] == "failed":
                    raise AnalysisAlreadyFailedError(
                        "이미 실패한 재개 요청입니다. 이력을 확인하세요."
                    )
                raise AnalysisAlreadyRunningError("동일 답변으로 최종판단을 실행 중입니다.")
            bundle = await asyncio.to_thread(
                repository.load_resume_context, submission.request_id, db_path=path
            )
            result = await _evaluate_saved(bundle, generate=generate)
            await _settle(
                asyncio.to_thread(
                    repository.complete_request,
                    result,
                    source_attempts=bundle["source_attempts"],
                    db_path=path,
                )
            )
            return result
    except (Exception, asyncio.CancelledError) as exc:
        if owned:
            await _record_failure(submission.request_id, exc, path)
        raise


@overload
async def execute_analysis(
    address: str,
    *,
    db_path: str | Path | None = None,
    radius_m: int = DEFAULT_RADIUS_M,
    resolve: Callable[[str], Awaitable[Site]] | None = None,
    agents: AgentRegistry | None = None,
    generate: GenerateDecision | None = None,
    request_id: str | None = None,
    agent_timeout: float | None = None,
    overall_timeout: float | None = None,
    settings: ExecutionSettings | None = None,
    supplements: list[SupplementTool] | None = None,
    on_supplement: OnSupplement | None = None,
    allow_questions: Literal[False] = False,
    map_lookup: MapLookup | None = None,
) -> DecisionResult: ...


@overload
async def execute_analysis(
    address: str,
    *,
    db_path: str | Path | None = None,
    radius_m: int = DEFAULT_RADIUS_M,
    resolve: Callable[[str], Awaitable[Site]] | None = None,
    agents: AgentRegistry | None = None,
    generate: GenerateDecision | None = None,
    request_id: str | None = None,
    agent_timeout: float | None = None,
    overall_timeout: float | None = None,
    settings: ExecutionSettings | None = None,
    supplements: list[SupplementTool] | None = None,
    on_supplement: OnSupplement | None = None,
    allow_questions: bool,
    map_lookup: MapLookup | None = None,
) -> DecisionResult | WaitingForInput: ...


async def execute_analysis(
    address: str,
    *,
    db_path: str | Path | None = None,
    radius_m: int = DEFAULT_RADIUS_M,
    resolve: Callable[[str], Awaitable[Site]] | None = None,
    agents: AgentRegistry | None = None,
    generate: GenerateDecision | None = None,
    request_id: str | None = None,
    agent_timeout: float | None = None,
    overall_timeout: float | None = None,
    settings: ExecutionSettings | None = None,
    supplements: list[SupplementTool] | None = None,
    on_supplement: OnSupplement | None = None,
    allow_questions: bool = False,
    map_lookup: MapLookup | None = None,
) -> DecisionResult | WaitingForInput:
    """요청·중간 결과·최종 결과를 저장하며 실패는 호출자에게 전달합니다."""
    radius_m = validate_radius(radius_m)
    if map_lookup is not None and not callable(map_lookup):
        raise ValueError("지도 조회 함수가 필요합니다.")
    if type(allow_questions) is not bool:
        raise ValueError("질문 허용 여부는 참 또는 거짓이어야 합니다.")
    supplements = list(supplements or [])
    validate_tools(supplements)
    if not isinstance(address, str) or not address.strip():
        raise ValueError("주소가 비어 있습니다.")
    if request_id is None:
        request_id = uuid.uuid4().hex
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("요청 ID가 비어 있습니다.")
    request_id = request_id.strip()
    settings = settings or ExecutionSettings.from_env()
    resolve = resolve if resolve is not None else partial(resolve_site, settings=settings.address)
    agents = agents if agents is not None else build_react_agents(settings)
    generate = generate or partial(decision.generate_decision, settings=settings.decision_llm)
    db_path = db_path if db_path is not None else settings.db_path
    agent_timeout = settings.agent_timeout if agent_timeout is None else agent_timeout
    overall_timeout = settings.overall_timeout if overall_timeout is None else overall_timeout
    if set(agents) != set(AGENT_IDS) or not all(callable(agent) for agent in agents.values()):
        raise ValueError("세 분석 에이전트의 호출 함수를 등록해 주세요.")
    if not callable(resolve):
        raise ValueError("주소 변환 함수가 필요합니다.")

    if not callable(generate) or (on_supplement is not None and not callable(on_supplement)):
        raise ValueError("판단·보완 알림은 호출 가능한 함수여야 합니다.")
    validate_timeout(agent_timeout)
    validate_timeout(overall_timeout)
    owned = False
    source_attempts = dict.fromkeys(AGENT_IDS, 1)

    async def create() -> None:
        nonlocal owned
        await asyncio.to_thread(
            repository.create_request, request_id, address, radius_m=radius_m, db_path=path
        )
        owned = True

    async def save_task(task: AnalysisTask) -> None:
        await _settle(asyncio.to_thread(repository.save_site, task, db_path=path))

    async def start_map(task: AnalysisTask, plan: MapLookupPlan) -> None:
        await _settle(asyncio.to_thread(repository.start_map_lookup, task, plan, db_path=path))

    async def save_map(observation: MapObservation) -> None:
        await _settle(asyncio.to_thread(repository.complete_map_lookup, observation, db_path=path))

    async def save_analysis(analysis: AgentAnalysis) -> None:
        await _settle(asyncio.to_thread(repository.save_agent, analysis, db_path=path))

    async def save_supplement(event: SupplementEvent) -> None:
        await _settle(asyncio.to_thread(repository.save_supplement_event, event, db_path=path))
        if event.adopted:
            source_attempts[event.request.agent_id] = 2
        if on_supplement is not None:
            await on_supplement(event.model_copy(deep=True))

    async def save_questions(
        task: AnalysisTask, waiting: WaitingForInput, done: bool, feedback: list[str]
    ) -> None:
        snapshot = QuestionSnapshot(
            task=task,
            waiting=waiting,
            source_attempts=source_attempts,
            supplement_done=done,
            feedback=feedback,
        )

        async def persist() -> None:
            nonlocal owned
            await asyncio.to_thread(repository.save_question_snapshot, snapshot, db_path=path)
            # 대기 이후 실행은 답변을 선점한 호출이 소유합니다.
            owned = False

        await _settle(persist())

    try:
        async with asyncio.timeout(overall_timeout):
            path = await _settle(asyncio.to_thread(initialize, db_path))
            # INSERT 성공을 확인한 호출만 이 요청의 실패 상태를 변경할 수 있습니다.
            await _settle(create())
            await _settle(asyncio.to_thread(repository.mark_running, request_id, db_path=path))
            result = await run_graph(
                address,
                radius_m=radius_m,
                resolve=resolve,
                agents=agents,
                request_id=request_id,
                generate=generate,
                agent_timeout=agent_timeout,
                supplements=supplements,
                allow_questions=allow_questions,
                map_lookup=map_lookup,
                hooks=RunHooks(
                    on_task_prepared=save_task,
                    on_analysis_completed=save_analysis,
                    on_supplement=save_supplement,
                    on_map_requested=start_map,
                    on_map_completed=save_map,
                    on_questions=save_questions if allow_questions else None,
                ),
            )
            if isinstance(result, WaitingForInput):
                return result
            await _settle(
                asyncio.to_thread(
                    repository.complete_request,
                    result,
                    source_attempts=source_attempts,
                    db_path=path,
                )
            )
            return result
    except (Exception, asyncio.CancelledError) as exc:
        if owned:
            await _record_failure(request_id, exc, path)
        raise


async def retry_decision(
    request_id: str,
    *,
    failed_at: str,
    settings: ExecutionSettings | None = None,
    generate: GenerateDecision | None = None,
) -> DecisionResult:
    """데이터를 재조회하지 않고 저장된 자료로 최종판단만 다시 실행합니다."""
    settings = settings or ExecutionSettings.from_env()
    if generate is None:
        settings.decision_llm.require_credentials()
        generate = partial(decision.generate_decision, settings=settings.decision_llm)
    if not callable(generate):
        raise ValueError("최종판단 호출 함수가 필요합니다.")
    bundle: dict[str, Any] | None = None
    path = await _settle(asyncio.to_thread(initialize, settings.db_path))

    async def claim() -> None:
        nonlocal bundle
        bundle = await asyncio.to_thread(
            repository.claim_decision_retry, request_id, failed_at, db_path=path
        )

    try:
        async with asyncio.timeout(settings.overall_timeout):
            await _settle(claim())
            assert bundle is not None
            source_attempts = bundle["source_attempts"]
            result = await _evaluate_saved(bundle, generate=generate)
            await _settle(
                asyncio.to_thread(
                    repository.complete_request,
                    result,
                    source_attempts=source_attempts,
                    db_path=path,
                )
            )
            return result
    except (Exception, asyncio.CancelledError) as exc:
        if bundle is not None:
            await _record_failure(request_id, exc, path, retry=True)
        raise


async def _evaluate_saved(bundle: dict[str, Any], *, generate: GenerateDecision) -> DecisionResult:
    """저장된 입력으로 판단만 실행하며 추가 외부 조회를 허용하지 않습니다."""
    result = await decision.evaluate(
        bundle["request"],
        site=bundle["site"],
        user_answers=bundle["answers"],
        feedback=bundle["feedback"],
        supplement_context=bundle["supplement_context"],
        generate=generate,
    )
    if not isinstance(result, DecisionResult):
        raise ValueError("재개 후에는 최종판단만 허용합니다.")
    return result


def _failure_code(error: BaseException, *, retry: bool = False) -> str:
    if isinstance(error, decision.DecisionContractError):
        return error.code
    if retry:
        return "DECISION_RETRY_FAILED"
    if isinstance(error, asyncio.CancelledError):
        return "ANALYSIS_CANCELLED"
    if isinstance(error, TimeoutError):
        return "ANALYSIS_TIMEOUT"
    if isinstance(error, sqlite3.Error):
        return "STORAGE_ERROR"
    return "ANALYSIS_FAILED"


async def _record_failure(
    request_id: str, error: BaseException, path: Path, *, retry: bool = False
) -> None:
    """소유한 미완료 요청만 실패로 기록하고 원래 예외를 보존합니다."""

    def persist() -> None:
        row = repository.get_request(request_id, db_path=path)
        if row and row["status"] in {"pending", "running"}:
            messages = {
                "DECISION_CONTRACT_INVALID": "최종판단의 업종 또는 근거 검증에 실패했습니다.",
                "ANALYSIS_CANCELLED": "분석 요청이 취소되었습니다.",
                "ANALYSIS_TIMEOUT": "분석 제한시간이 초과되었습니다.",
                "STORAGE_ERROR": "분석 결과를 저장하지 못했습니다. 저장소 상태를 확인해 주세요.",
            }
            repository.fail_request(
                request_id,
                AgentError(
                    code=_failure_code(error, retry=retry),
                    # 재시도 가능 코드는 유지하고 원인은 원문 없이 구분합니다.
                    message=messages.get(
                        _failure_code(error),
                        "최종판단 재시도에 실패했습니다." if retry else "분석 실행에 실패했습니다.",
                    ),
                ),
                diagnostics=getattr(error, "failures", None),
                db_path=path,
            )

    try:
        await _settle(asyncio.to_thread(persist))
    except asyncio.CancelledError:
        raise
    except Exception:
        error.add_note("DB 실패 상태를 기록하지 못했습니다. 기존 상태를 확인해 주세요.")
