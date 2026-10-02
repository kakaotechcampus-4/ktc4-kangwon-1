"""오케스트레이터 실행 중 검증된 결과를 SQLite에 저장합니다."""

import asyncio
import json
import logging
import sqlite3
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import replace
from functools import partial
from pathlib import Path
from time import monotonic
from typing import Any, Literal, overload

from app.address import resolve_site
from app.agents.decision import agent as decision
from app.agents.decision.agent import GenerateDecision
from app.agents.evaluators.agent import GenerateEvaluation, generate_evaluation
from app.agents.orchestration.graph import RunHooks, run_graph
from app.agents.orchestration.nodes.decision import evaluate_with_log
from app.agents.orchestration.supplement import OnSupplement, validate_tools
from app.agents.orchestration.tools import MapLookup, SupplementTool
from app.agents.orchestration.validation import (
    validate_address,
    validate_agents,
    validate_allow_questions,
    validate_evaluators,
    validate_map_lookup,
    validate_request_id,
    validate_specialists,
)
from app.agents.orchestration.workflow import (
    AgentRegistry,
    build_react_agents,
    build_supplement_tools,
)
from app.agents.specialists.agent import GenerateSpecialist, generate_specialist
from app.db import repository
from app.db.connection import initialize
from app.llm.budget import (
    EVALUATED_MAX_CALLS,
    MAX_CALLS,
    BudgetExceeded,
    BudgetStorageError,
    LLMBudget,
    llm_scope,
)
from app.logging import log_exception
from app.schemas import (
    AGENT_IDS,
    DEFAULT_RADIUS_M,
    EVALUATOR_IDS,
    AgentError,
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
from app.services.settings import ExecutionSettings, validate_timeout

logger = logging.getLogger(__name__)


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
            except Exception as exc:
                log_exception(logger, "취소 대기 중 저장 작업 실패", exc)
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
    generate_specialists: dict[SpecialistId, GenerateSpecialist] | None = None,
    supplements: list[SupplementTool] | None = None,
    map_lookup: MapLookup | None = None,
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
        owned = await asyncio.to_thread(repository.claim_question_resume, submission, db_path=path)

    try:
        path = await _settle(asyncio.to_thread(initialize, db_path))
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
            bundle = await asyncio.to_thread(
                repository.load_resume_context, submission.request_id, db_path=path
            )
            evaluation_state = await _saved_evaluation(bundle, path)
            async with _execution_scope(submission.request_id, path, timeout) as flush:
                if bundle["analysis_mode"] == "multi_agent":
                    capabilities = bundle["execution"].get("capabilities", {})
                    if capabilities.get("map"):
                        from app.agents.map_analysis.agent import observe

                        map_lookup = map_lookup or observe
                    else:
                        map_lookup = None
                    permitted = {tuple(key) for key in capabilities.get("supplements", [])}
                    supplements = [
                        t
                        for t in (
                            build_supplement_tools(settings) if supplements is None else supplements
                        )
                        if (t.operation.agent_id, t.operation.operation) in permitted
                    ]
                    experts = build_specialist_generators(
                        settings, generate_specialists, with_map=map_lookup is not None
                    )
                    result = await run_graph(
                        bundle["task"].site.input_address,
                        radius_m=bundle["task"].radius_m,
                        request_id=submission.request_id,
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
                            path, bundle["source_attempts"], request_id=submission.request_id
                        ),
                        resume_state={
                            **evaluation_state,
                            "task": bundle["task"],
                            "analyses": bundle["request"].analyses,
                            "briefs": bundle["briefs"],
                            "answers": bundle["specialist_answers"],
                            "consult_round": bundle["consult_round"],
                            "map_observation": bundle["request"].map_observation,
                            "map_queries": bundle["map_queries"],
                            "feedback": bundle["feedback"],
                            "supplement_context": bundle["supplement_context"],
                        },
                    )
                    if not isinstance(result, DecisionResult):
                        raise ValueError("재개 후에는 질문을 발행할 수 없습니다.")
                else:
                    result = await _evaluate_saved(bundle, generate=generate, path=path)
                await flush()
                await _settle(
                    asyncio.to_thread(
                        repository.complete_request,
                        result,
                        source_attempts=bundle["source_attempts"],
                        db_path=path,
                    )
                )
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
    generate_specialists: dict[SpecialistId, GenerateSpecialist] | None = None,
    generate_evaluators: dict[EvaluatorId, GenerateEvaluation] | None = None,
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
                brief_agents=[b.agent_id for b in state["briefs"]],
                consult_round=state["consult_round"],
                map_attempt=state["map_attempt"],
                llm_calls=state["execution"].get("budget", {}).get("used", 0),
                elapsed_seconds=state["execution"].get("elapsed_seconds", 0),
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
            await _settle(
                asyncio.to_thread(
                    repository.update_execution_state,
                    request_id,
                    db_path=path,
                    capabilities={
                        "evaluators": settings.evaluators_enabled,
                        "map": map_lookup is not None,
                        "supplements": [
                            [t.operation.agent_id, t.operation.operation] for t in supplements
                        ],
                    },
                    time_limit=overall_timeout if settings.evaluators_enabled else None,
                )
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
                await flush()
                await _settle(
                    asyncio.to_thread(
                        repository.complete_request,
                        result,
                        source_attempts=source_attempts,
                        db_path=path,
                    )
                )
            await _emit(path, request_id, "run", "completed", status=result.status)
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
    generate_evaluators: dict[EvaluatorId, GenerateEvaluation] | None = None,
) -> DecisionResult:
    """저장 자료로 재시도하며 평가 전 실패는 초안부터, 평가 후 실패는 최종판단만 실행합니다."""
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
        time_limit = await _saved_time_limit(request_id, path, settings.overall_timeout)
        async with asyncio.timeout(time_limit):
            await _settle(claim())
            assert bundle is not None
            source_attempts = bundle["source_attempts"]
            async with _execution_scope(request_id, path, time_limit) as flush:
                execution = bundle["execution"]
                saved = await asyncio.to_thread(repository.get_evaluation, request_id, db_path=path)
                if (
                    execution.get("capabilities", {}).get("evaluators")
                    and saved is None
                    and not execution.get("evaluation_skipped")
                ):
                    if "evaluation_start_round" in execution:
                        raise ValueError("이미 수행한 평가 기록이 없습니다.")
                    result = await run_graph(
                        bundle["request"].address,
                        request_id=request_id,
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
                        hooks=_storage_hooks(path, source_attempts, request_id=request_id),
                        resume_state={
                            "task": bundle["task"],
                            "analyses": bundle["request"].analyses,
                            "map_observation": bundle["request"].map_observation,
                            "map_done": bundle["request"].map_observation is not None,
                            "supplement_done": bool(bundle["supplement_context"]),
                            "feedback": bundle["feedback"],
                            "supplement_context": bundle["supplement_context"],
                            "briefs": bundle["briefs"],
                            "answers": bundle["specialist_answers"],
                            "consult_round": bundle["consult_round"],
                            "map_queries": bundle["map_queries"],
                        },
                    )
                    if not isinstance(result, DecisionResult):
                        raise ValueError("재시도 후에는 최종판단만 허용합니다.")
                else:
                    result = await _evaluate_saved(bundle, generate=generate, path=path)
                await flush()
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


async def _evaluate_saved(
    bundle: dict[str, Any], *, generate: GenerateDecision, path=None
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
                diagnostics=getattr(error, "failures", None),
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
    execution = json.loads(row["execution_json"])
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


def build_evaluator_generators(settings, injected=None):
    if injected is not None:
        validate_evaluators(injected)
        return injected
    return {
        role: partial(generate_evaluation, settings=settings.evaluator_llm)
        for role in EVALUATOR_IDS
    }


def build_specialist_generators(settings, injected=None, *, with_map=False):
    roles = [*AGENT_IDS, *(["map_analysis"] if with_map else [])]
    if injected is not None:
        validate_specialists(injected, with_map=with_map)
        return injected
    return {
        role: partial(
            generate_specialist, settings=settings.specialist_llms.get(role, settings.decision_llm)
        )
        for role in roles
    }


async def _emit(path, request_id: str, stage: str, event: str, **detail) -> None:
    """진행 이벤트는 화면 표시용이라 저장 실패가 분석을 멈추지 않게 기록만 남깁니다."""
    try:
        await _settle(
            asyncio.to_thread(
                repository.append_event, request_id, stage, event, detail, db_path=path
            )
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log_exception(logger, "진행 이벤트 저장 실패: %s %s", exc, stage, event)


def _storage_hooks(path, source_attempts, on_supplement=None, *, request_id=None) -> RunHooks:
    async def write(fn, *args, **kwargs):
        return await _settle(asyncio.to_thread(fn, *args, db_path=path, **kwargs))

    async def save_task(task):
        await write(repository.save_site, task)

    async def save_analysis(analysis):
        await write(repository.save_agent, analysis)

    async def start_map(task, plan):
        await write(repository.start_map_lookup, task, plan)

    async def save_map(observation, adopted=True):
        await write(repository.complete_map_lookup, observation, adopted=adopted)

    async def save_supplement(event):
        attempt = await write(repository.save_supplement_event, event)
        if event.adopted:
            source_attempts[event.request.agent_id] = attempt
        if on_supplement is not None:
            await on_supplement(event.model_copy(deep=True))

    async def save_brief(brief):
        await write(repository.save_agent_brief, brief)

    async def save_answer(answer):
        await write(repository.save_specialist_answer, answer)

    async def save_evaluation(draft, evaluations):
        await write(repository.save_evaluation, draft, evaluations)

    async def save_log(entries):
        await write(repository.save_evaluation_log, request_id, entries)

    async def on_step(stage, event, detail):
        if stage == "evaluate" and "skipped" in detail:
            await write(
                repository.update_execution_state, request_id, evaluation_skipped=detail["skipped"]
            )
        await _emit(path, request_id, stage, event, **detail)

    return RunHooks(
        on_evaluation=save_evaluation,
        on_evaluation_log=save_log,
        on_task_prepared=save_task,
        on_analysis_completed=save_analysis,
        on_supplement=save_supplement,
        on_map_requested=start_map,
        on_map_completed=save_map,
        on_map_result=save_map,
        on_brief=save_brief,
        on_consult=save_answer,
        on_step=on_step if request_id else None,
    )


@asynccontextmanager
async def _execution_scope(request_id, path, time_limit, *, active=lambda: True):
    """사람의 대기 시간은 제외하고 요청의 호출·활성 시간 예산을 이어 씁니다."""
    row = await asyncio.to_thread(repository.get_request, request_id, db_path=path)
    saved = json.loads(row["execution_json"])
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
