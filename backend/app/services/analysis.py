"""오케스트레이터 실행 중 검증된 결과를 SQLite에 저장합니다."""

import asyncio
import json
import logging
import sqlite3
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from functools import partial
from pathlib import Path
from time import monotonic
from typing import Literal, cast, overload

from app.address import resolve_site
from app.agents.decision import agent as decision
from app.agents.decision.agent import GenerateDecision
from app.agents.evaluators.agent import GenerateEvaluation
from app.agents.orchestration.graph import run_graph
from app.agents.orchestration.nodes.decision import evaluate_with_log
from app.agents.orchestration.state import GraphState
from app.agents.orchestration.supplement import OnSupplement, validate_tools
from app.agents.orchestration.tools import MapLookup, SupplementTool, ZoneLookup
from app.agents.orchestration.validation import (
    validate_address,
    validate_agents,
    validate_allow_questions,
    validate_map_lookup,
    validate_request_id,
)
from app.agents.orchestration.workflow import (
    AgentRegistry,
    build_react_agents,
    build_supplement_tools,
)
from app.agents.specialists.agent import GenerateSpecialist
from app.db import repository
from app.db.analysis_repository import SqliteAnalysisRepository
from app.db.connection import initialize
from app.db.types import ExecutionState, ResumeBundle
from app.education_zone import scan_site, site_lookup
from app.execution.errors import (
    DecisionExecutionError,
    capture_decision_failures,
    failure_diagnostics,
)
from app.execution.validation import validate_execution_state
from app.llm.budget import (
    EVALUATED_MAX_CALLS,
    MAX_CALLS,
    BudgetExceeded,
    BudgetStorageError,
    LLMBudget,
    llm_scope,
)
from app.llm.session import with_client_session
from app.logging import log_exception
from app.schemas import (
    AGENT_IDS,
    DEFAULT_RADIUS_M,
    AgentError,
    AgentId,
    AnalysisTask,
    AnswerSubmission,
    DecisionResult,
    EvaluatorId,
    QuestionSnapshot,
    QuestionSnapshotV2,
    Site,
    SpecialistId,
    WaitingForInput,
    validate_radius,
)
from app.services.generators import build_evaluator_generators, build_specialist_generators
from app.services.persistence import _emit, _settle, _storage_hooks
from app.services.settings import ExecutionSettings, validate_timeout
from app.storage.contracts import AnalysisRepositoryProtocol

logger = logging.getLogger(__name__)


class AnalysisAlreadyRunningError(RuntimeError):
    """동일 답변으로 이미 실행 중인 요청입니다."""


class AnalysisAlreadyFailedError(RuntimeError):
    """이미 실패한 답변 실행은 자동 재시도하지 않습니다."""


@capture_decision_failures
@with_client_session
async def resume_analysis(
    submission: AnswerSubmission,
    *,
    db_path: str | Path | None = None,
    generate: GenerateDecision | None = None,
    settings: ExecutionSettings | None = None,
    overall_timeout: float | None = None,
    generate_specialists: dict[SpecialistId, GenerateSpecialist] | None = None,
    supplements: list[SupplementTool] | None = None,
    map_lookup: MapLookup | None = None,
    find_zones: ZoneLookup | None = None,
    generate_evaluators: dict[EvaluatorId, GenerateEvaluation] | None = None,
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
        owned = await asyncio.to_thread(storage.claim_answers, submission)

    try:
        path = await _settle(asyncio.to_thread(initialize, db_path))
        storage: AnalysisRepositoryProtocol = SqliteAnalysisRepository(path)
        timeout = await _saved_time_limit(submission.request_id, path, timeout)
        async with asyncio.timeout(timeout):
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
            bundle = await asyncio.to_thread(storage.load_resume, submission.request_id)
            evaluation_state = await _saved_evaluation(bundle, path)
            async with _execution_scope(submission.request_id, path, timeout) as flush:
                if bundle["analysis_mode"] == "multi_agent":
                    result = await _resume_graph(
                        bundle,
                        path,
                        settings,
                        generate,
                        generate_specialists,
                        generate_evaluators,
                        supplements,
                        map_lookup,
                        evaluation_state,
                        find_zones,
                    )
                else:
                    result = await _evaluate_saved(bundle, generate=generate, path=path)
                await _complete(result, flush, path, bundle["source_attempts"], storage=storage)
            await _emit(path, submission.request_id, "run", "completed", status=result.status)
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
    find_zones: ZoneLookup | None = None,
    generate_specialists: dict[SpecialistId, GenerateSpecialist] | None = None,
    generate_evaluators: dict[EvaluatorId, GenerateEvaluation] | None = None,
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
    find_zones: ZoneLookup | None = None,
    generate_specialists: dict[SpecialistId, GenerateSpecialist] | None = None,
    generate_evaluators: dict[EvaluatorId, GenerateEvaluation] | None = None,
) -> DecisionResult | WaitingForInput: ...


@capture_decision_failures
@with_client_session
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
    find_zones: ZoneLookup | None = None,
    generate_specialists: dict[SpecialistId, GenerateSpecialist] | None = None,
    generate_evaluators: dict[EvaluatorId, GenerateEvaluation] | None = None,
) -> DecisionResult | WaitingForInput:
    """요청·중간 결과·최종 결과를 저장하며 실패는 호출자에게 전달합니다."""
    radius_m = validate_radius(radius_m)
    validate_map_lookup(map_lookup)
    validate_allow_questions(allow_questions)
    supplements = list(supplements or [])
    validate_tools(supplements)
    validate_address(address)
    if request_id is None:
        request_id = uuid.uuid4().hex
    validate_request_id(request_id)
    request_id = request_id.strip()
    settings = settings or ExecutionSettings.from_env()
    resolve = resolve if resolve is not None else partial(resolve_site, settings=settings.address)
    # 인증키가 없으면 None이라 조회 자체를 걸지 않습니다.
    find_zones = find_zones if find_zones is not None else site_lookup()
    agents = agents if agents is not None else build_react_agents(settings)
    generate = generate or partial(decision.generate_decision, settings=settings.decision_llm)
    db_path = db_path if db_path is not None else settings.db_path
    agent_timeout = settings.agent_timeout if agent_timeout is None else agent_timeout
    overall_timeout = settings.overall_timeout if overall_timeout is None else overall_timeout
    validate_agents(agents)
    if not callable(resolve):
        raise ValueError("주소 변환 함수가 필요합니다.")

    if not callable(generate) or (on_supplement is not None and not callable(on_supplement)):
        raise ValueError("판단·보완 알림은 호출 가능한 함수여야 합니다.")
    validate_timeout(agent_timeout)
    validate_timeout(overall_timeout)
    experts = (
        build_specialist_generators(settings, generate_specialists, with_map=map_lookup is not None)
        if settings.analysis_mode == "multi_agent"
        else None
    )
    evaluators = (
        build_evaluator_generators(settings, generate_evaluators)
        if settings.evaluators_enabled
        else None
    )
    return await _execute_new(
        address,
        request_id,
        settings,
        db_path,
        radius_m,
        resolve,
        agents,
        generate,
        agent_timeout,
        overall_timeout,
        supplements,
        on_supplement,
        allow_questions,
        map_lookup,
        find_zones,
        experts,
        evaluators,
    )


@capture_decision_failures
@with_client_session
async def retry_decision(
    request_id: str,
    *,
    failed_at: str,
    settings: ExecutionSettings | None = None,
    generate: GenerateDecision | None = None,
    generate_evaluators: dict[EvaluatorId, GenerateEvaluation] | None = None,
) -> DecisionResult:
    """저장 자료로 재시도하며 평가 전 실패는 초안부터, 평가 후 실패는 최종판단만 실행합니다."""
    settings = settings or ExecutionSettings.from_env()
    if generate is None:
        settings.decision_llm.require_credentials()
        generate = partial(decision.generate_decision, settings=settings.decision_llm)
    if not callable(generate):
        raise ValueError("최종판단 호출 함수가 필요합니다.")
    bundle: ResumeBundle | None = None
    path = await _settle(asyncio.to_thread(initialize, settings.db_path))
    storage: AnalysisRepositoryProtocol = SqliteAnalysisRepository(path)

    async def claim() -> None:
        nonlocal bundle
        bundle = await asyncio.to_thread(storage.claim_retry, request_id, failed_at)

    try:
        time_limit = await _saved_time_limit(request_id, path, settings.overall_timeout)
        async with asyncio.timeout(time_limit):
            await _settle(claim())
            assert bundle is not None
            source_attempts = bundle["source_attempts"]
            async with _execution_scope(request_id, path, time_limit) as flush:
                result = await _retry_saved(bundle, path, settings, generate, generate_evaluators)
                await _complete(result, flush, path, source_attempts, storage=storage)
            return result
    except (Exception, asyncio.CancelledError) as exc:
        if bundle is not None:
            await _record_failure(request_id, exc, path, retry=True)
        raise


async def _evaluate_saved(
    bundle: ResumeBundle, *, generate: GenerateDecision, path=None
) -> DecisionResult:
    """저장된 입력으로 판단만 실행하며 추가 외부 조회를 허용하지 않습니다."""
    state = await _saved_evaluation(bundle, path) if path is not None else {}
    result, entries = await evaluate_with_log(
        state,
        bundle["request"],
        site=bundle["site"],
        user_answers=bundle["answers"],
        feedback=bundle["feedback"],
        supplement_context=bundle["supplement_context"],
        generate=generate,
        deliberation={
            "briefs": bundle["briefs"],
            "answers": bundle["specialist_answers"],
            "specialists": [],
            "consult_round": bundle["consult_round"],
        }
        if bundle["analysis_mode"] == "multi_agent"
        else None,
    )
    if not isinstance(result, DecisionResult):
        raise ValueError("재개 후에는 최종판단만 허용합니다.")
    if state:
        await _settle(
            asyncio.to_thread(
                repository.save_evaluation_log, result.request_id, entries, db_path=path
            )
        )
    return result


def _failure_code(error: BaseException, *, retry: bool = False) -> str:
    if isinstance(error, DecisionExecutionError):
        error = error.error
    if isinstance(error, decision.DecisionContractError):
        return error.code
    if isinstance(error, BudgetStorageError):
        return "STORAGE_ERROR"
    if isinstance(error, BudgetExceeded):
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
                "LLM_BUDGET_EXHAUSTED": "요청의 모델 호출 예산을 모두 사용했습니다.",
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
                diagnostics=failure_diagnostics(error),
                db_path=path,
            )

    try:
        await _settle(asyncio.to_thread(persist))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log_exception(logger, "실패 상태 저장 실패: %s", exc, request_id)
        error.add_note("DB 실패 상태를 기록하지 못했습니다. 기존 상태를 확인해 주세요.")
        return
    await _emit(path, request_id, "run", "failed", code=_failure_code(error, retry=retry))


async def _saved_time_limit(request_id, path, fallback):
    row = await asyncio.to_thread(repository.get_request, request_id, db_path=path)
    state = json.loads(row["execution_json"]) if row else {}
    return (
        state.get("time_limit", fallback)
        if state.get("capabilities", {}).get("evaluators")
        else fallback
    )


async def _saved_evaluation(bundle, path):
    request = bundle["request"]
    row = await asyncio.to_thread(repository.get_request, request.request_id, db_path=path)
    execution: ExecutionState = json.loads(row["execution_json"])
    if not execution.get("capabilities", {}).get("evaluators"):
        return {}
    saved = await asyncio.to_thread(repository.get_evaluation, request.request_id, db_path=path)
    if saved is None:
        if execution.get("evaluation_skipped") in {"no_data", "budget"}:
            return {}
        raise ValueError("평가자 사용 요청의 평가 기록이 없습니다.")
    draft = DecisionResult(
        **saved["draft"],
        schema_version="1.0",
        agent_id="decision",
        address=request.address,
        status="ok",
        source_analyses=request.analyses,
        limitations=[],
    )
    return {
        "draft": draft,
        "evaluations": saved["evaluations"],
        "evaluation_start_round": execution.get("evaluation_start_round", 0),
    }


@asynccontextmanager
async def _execution_scope(request_id, path, time_limit, *, active=lambda: True):
    """사람의 대기 시간은 제외하고 요청의 호출·활성 시간 예산을 이어 씁니다."""
    row = await asyncio.to_thread(repository.get_request, request_id, db_path=path)
    saved: ExecutionState = json.loads(row["execution_json"])
    validate_execution_state(saved)
    enabled = saved.get("capabilities", {}).get("evaluators", False)
    if enabled:
        time_limit = saved.get("time_limit", time_limit)
    if row["analysis_mode"] != "multi_agent" and not enabled:

        async def noop():
            pass

        yield noop
        return
    elapsed = saved.get("elapsed_seconds", 0)
    started = monotonic()

    async def persist(budget=None):
        await _settle(
            asyncio.to_thread(
                repository.update_execution_state,
                request_id,
                budget=budget,
                elapsed_seconds=elapsed + monotonic() - started,
                db_path=path,
            )
        )

    async def flush():
        await persist()

    async def finish():
        if not active():
            return
        current = await asyncio.to_thread(repository.get_request, request_id, db_path=path)
        if current["status"] == "running":
            await flush()

    budget = LLMBudget(
        limit=EVALUATED_MAX_CALLS if enabled else MAX_CALLS,
        **saved.get("budget", {}),
        on_change=persist,
    )
    try:
        if time_limit <= elapsed:
            raise TimeoutError("요청의 누적 실행 제한시간을 초과했습니다.")
        with llm_scope(budget, "decision", final=True):
            async with asyncio.timeout(time_limit - elapsed):
                yield flush
    except BaseException as exc:
        try:
            await finish()
        except (Exception, asyncio.CancelledError):
            exc.add_note("누적 실행 시간을 저장하지 못했습니다.")
        raise
    else:
        await finish()


def build_resume_state(bundle: ResumeBundle, *, retry: bool = False) -> GraphState:
    """저장 자료를 재개 상태로 옮기고 기존 경로별 조회 완료 플래그를 보존합니다."""
    state: GraphState = {
        "task": bundle["task"],
        "analyses": bundle["request"].analyses,
        "briefs": bundle["briefs"],
        "answers": bundle["specialist_answers"],
        "consult_round": bundle["consult_round"],
        "map_queries": bundle["map_queries"],
        "feedback": bundle["feedback"],
        "supplement_context": bundle["supplement_context"],
    }
    state["map_observation"] = bundle["request"].map_observation
    if retry:
        state["map_done"] = bundle["request"].map_observation is not None
        state["supplement_done"] = bool(bundle["supplement_context"])
    return state


async def _complete(
    result, flush, path, source_attempts, *, storage: AnalysisRepositoryProtocol | None = None
):
    """예산 저장을 끝낸 뒤 그 실행이 사용한 분석 차수로 완료합니다."""
    await flush()
    storage = storage if storage is not None else SqliteAnalysisRepository(path)
    await _settle(
        asyncio.to_thread(
            storage.complete,
            result,
            attempt=1,
            source_attempts=source_attempts,
        )
    )


async def _resume_graph(
    bundle: ResumeBundle,
    path,
    settings,
    generate,
    generate_specialists,
    generate_evaluators,
    supplements,
    map_lookup,
    evaluation_state,
    find_zones=None,
):
    capabilities = bundle["execution"].get("capabilities", {})
    if capabilities.get("map"):
        from app.agents.map_analysis.agent import observe

        map_lookup = map_lookup or observe
    else:
        map_lookup = None
    permitted = {tuple(key) for key in capabilities.get("supplements", [])}
    supplements = [
        t
        for t in (build_supplement_tools(settings) if supplements is None else supplements)
        if (t.operation.agent_id, t.operation.operation) in permitted
    ]
    experts = build_specialist_generators(
        settings, generate_specialists, with_map=map_lookup is not None
    )
    # 재개는 주소 노드를 건너뛰므로 보호구역을 여기서 한 번 더 확보합니다.
    scan = await scan_site(bundle["task"].site, find_zones or site_lookup())
    zones: GraphState = {"education_zones": scan} if scan is not None else {}
    result = await run_graph(
        bundle["task"].site.input_address,
        radius_m=bundle["task"].radius_m,
        request_id=bundle["request"].request_id,
        resolve=partial(resolve_site, settings=settings.address),
        agents=build_react_agents(settings),
        generate=generate,
        mode="multi_agent",
        generate_specialists=experts,
        evaluators_enabled=bool(evaluation_state),
        generate_evaluators=(
            generate_evaluators
            if generate_evaluators is not None
            else build_evaluator_generators(settings)
        )
        if evaluation_state
        else None,
        user_answers=bundle["answers"],
        supplements=supplements,
        map_lookup=map_lookup,
        agent_timeout=settings.agent_timeout,
        hooks=_storage_hooks(
            path, bundle["source_attempts"], request_id=bundle["request"].request_id
        ),
        resume_state={**evaluation_state, **build_resume_state(bundle), **zones},
    )
    if not isinstance(result, DecisionResult):
        raise ValueError("재개 후에는 질문을 발행할 수 없습니다.")
    return result


async def _retry_saved(bundle: ResumeBundle, path, settings, generate, generate_evaluators):
    execution = bundle["execution"]
    saved = await asyncio.to_thread(
        repository.get_evaluation, bundle["request"].request_id, db_path=path
    )
    if (
        execution.get("capabilities", {}).get("evaluators")
        and saved is None
        and not execution.get("evaluation_skipped")
    ):
        if "evaluation_start_round" in execution:
            raise ValueError("이미 수행한 평가 기록이 없습니다.")
        result = await run_graph(
            bundle["request"].address,
            request_id=bundle["request"].request_id,
            radius_m=bundle["task"].radius_m,
            resolve=partial(resolve_site, settings=settings.address),
            agents=build_react_agents(settings),
            generate=generate,
            mode=bundle["analysis_mode"],
            retry_only=True,
            evaluators_enabled=True,
            generate_evaluators=generate_evaluators
            if generate_evaluators is not None
            else build_evaluator_generators(settings),
            agent_timeout=settings.agent_timeout,
            user_answers=bundle["answers"],
            hooks=_storage_hooks(
                path, bundle["source_attempts"], request_id=bundle["request"].request_id
            ),
            resume_state=build_resume_state(bundle, retry=True),
        )
        if not isinstance(result, DecisionResult):
            raise ValueError("재시도 후에는 최종판단만 허용합니다.")
    else:
        result = await _evaluate_saved(bundle, generate=generate, path=path)
    return result


async def _execute_new(
    address,
    request_id,
    settings,
    db_path,
    radius_m,
    resolve,
    agents,
    generate,
    agent_timeout,
    overall_timeout,
    supplements,
    on_supplement,
    allow_questions,
    map_lookup,
    find_zones,
    experts,
    evaluators,
):
    owned = False
    source_attempts = dict.fromkeys(AGENT_IDS, 1)

    async def create() -> None:
        nonlocal owned
        await asyncio.to_thread(
            repository.create_request,
            request_id,
            address,
            radius_m=radius_m,
            analysis_mode=settings.analysis_mode,
            db_path=path,
        )
        owned = True

    async def save_questions(
        task: AnalysisTask, waiting: WaitingForInput, done: bool, feedback: list[str]
    ) -> None:
        snapshot = await _question_snapshot(
            task,
            waiting,
            done,
            feedback,
            source_attempts,
            settings,
            request_id,
            path,
            flush,
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
            await _start_execution(
                request_id, path, settings, map_lookup, supplements, overall_timeout
            )
            async with _execution_scope(
                request_id, path, overall_timeout, active=lambda: owned
            ) as flush:
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
                    find_zones=find_zones,
                    mode=settings.analysis_mode,
                    generate_specialists=experts,
                    evaluators_enabled=settings.evaluators_enabled,
                    generate_evaluators=evaluators,
                    hooks=replace(
                        _storage_hooks(path, source_attempts, on_supplement, request_id=request_id),
                        on_questions=save_questions if allow_questions else None,
                    ),
                )
                if isinstance(result, WaitingForInput):
                    return result
                await _complete(result, flush, path, source_attempts)
            await _emit(path, request_id, "run", "completed", status=result.status)
            return result
    except (Exception, asyncio.CancelledError) as exc:
        if owned:
            await _record_failure(request_id, exc, path)
        raise


async def _question_snapshot(
    task, waiting, done, feedback, source_attempts, settings, request_id, path, flush
):
    snapshot = QuestionSnapshot(
        task=task,
        waiting=waiting,
        source_attempts=source_attempts,
        supplement_done=done,
        feedback=feedback,
    )
    await flush()
    if settings.analysis_mode == "multi_agent":
        state = await asyncio.to_thread(repository.get_deliberation, request_id, db_path=path)
        events = await asyncio.to_thread(
            repository.list_supplement_events, request_id, db_path=path
        )
        snapshot = QuestionSnapshotV2(
            **{
                **snapshot.model_dump(mode="json"),
                "version": 2,
                "supplement_done": bool(events),
            },
            brief_agents=[cast(AgentId, b.agent_id) for b in state["briefs"]],
            consult_round=state["consult_round"],
            map_attempt=state["map_attempt"],
            llm_calls=state["execution"].get("budget", {}).get("used", 0),
            elapsed_seconds=state["execution"].get("elapsed_seconds", 0),
        )

    return snapshot


async def _start_execution(request_id, path, settings, map_lookup, supplements, overall_timeout):
    await _settle(asyncio.to_thread(repository.mark_running, request_id, db_path=path))
    await _settle(
        asyncio.to_thread(
            repository.update_execution_state,
            request_id,
            db_path=path,
            capabilities={
                "evaluators": settings.evaluators_enabled,
                "map": map_lookup is not None,
                "supplements": [[t.operation.agent_id, t.operation.operation] for t in supplements],
            },
            time_limit=overall_timeout if settings.evaluators_enabled else None,
        )
    )
