"""기존 도구 계약을 유지하며 판단·보완 분기를 그래프로 실행합니다."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, fields
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from app.agents.decision import agent as decision
from app.agents.decision.agent import GenerateDecision
from app.agents.evaluators.agent import GenerateEvaluation, decision_evaluation, evaluate_draft
from app.agents.specialists.agent import GenerateSpecialist, answer_query, write_brief
from app.llm.budget import EVALUATED_MAX_CALLS, MAX_CALLS, LLMBudget, current_scope, llm_scope
from app.schemas import (
    AGENT_IDS,
    EVALUATOR_IDS,
    QUESTION_FIELDS,
    AgentAnalysis,
    AgentBrief,
    AnalysisMode,
    AnalysisTask,
    ConsultPlan,
    DecisionRequest,
    DecisionResult,
    Evaluation,
    EvaluationLogEntry,
    EvaluationRequest,
    EvaluatorId,
    LandlordAnswer,
    MapLookupPlan,
    MapObservation,
    QuestionPlan,
    Site,
    SpecialistAnswer,
    SpecialistId,
    SupplementEvent,
    SupplementOperation,
    SupplementPlan,
    WaitingForInput,
    validate_radius,
)
from app.services.settings import validate_timeout

from . import tools, workflow
from .consult import build_specialist_tools
from .map import execute_map_lookup
from .supplement import OnSupplement, execute_supplement, validate_tools

# 브리핑은 도구 2회 + finish, 되묻기 답변은 도구 최대 4회 + finish입니다.
BRIEF_STEPS = 3
CONSULT_STEPS = 5
EVALUATOR_RESERVE = 4


def consult_steps(agent_id: str, share: int) -> int:
    """배정된 호출 몫 안에서 finish까지 끝낼 수 있는 차례 수입니다."""
    if agent_id == "map_analysis":
        # 지도 검색 한 번은 업종 매핑 모델 호출을 한 번 더 쓸 수 있습니다.
        share = 1 + (share - 1) // 2
    return max(1, min(CONSULT_STEPS, share))


class GraphState(TypedDict, total=False):
    """요청별 데이터만 보관하며 실행 함수와 비밀키는 포함하지 않습니다."""

    task: AnalysisTask
    analyses: list[AgentAnalysis]
    outcome: (
        DecisionResult
        | SupplementPlan
        | QuestionPlan
        | WaitingForInput
        | MapLookupPlan
        | ConsultPlan
    )
    map_done: bool
    map_observation: MapObservation
    operations: list[SupplementOperation]
    supplement_done: bool
    feedback: list[str]
    supplement_context: list[SupplementEvent]
    briefs: list[AgentBrief]
    answers: list[SpecialistAnswer]
    consult_round: int
    context: dict
    draft: DecisionResult
    evaluations: list[Evaluation]
    evaluation_start_round: int
    final_call: bool


@dataclass(frozen=True)
class RunHooks:
    """서비스가 관리하는 저장·관찰 콜백입니다."""

    on_task_prepared: Callable[[AnalysisTask], Awaitable[None]] | None = None
    on_analysis_completed: Callable[[AgentAnalysis], Awaitable[None]] | None = None
    on_supplement: OnSupplement | None = None
    on_map_requested: tools.OnMapRequested | None = None
    on_map_completed: tools.OnMapCompleted | None = None
    on_map_result: Callable[[MapObservation, bool], Awaitable[None]] | None = None
    on_brief: Callable[[AgentBrief], Awaitable[None]] | None = None
    on_consult: Callable[[SpecialistAnswer], Awaitable[None]] | None = None
    on_questions: (
        Callable[[AnalysisTask, WaitingForInput, bool, list[str]], Awaitable[None]] | None
    ) = None
    # 진행 화면용 단계 이벤트입니다. detail에는 코드가 정한 요약만 넣습니다.
    on_step: Callable[[str, str, dict], Awaitable[None]] | None = None
    on_evaluation: Callable[[DecisionResult, list[Evaluation]], Awaitable[None]] | None = None
    on_evaluation_log: Callable[[list[EvaluationLogEntry]], Awaitable[None]] | None = None


def action_of(outcome) -> str:
    """최종판단이 고른 다음 행동 이름입니다."""
    if isinstance(outcome, ConsultPlan):
        return "ask_specialists"
    if isinstance(outcome, SupplementPlan):
        return "supplement"
    if isinstance(outcome, MapLookupPlan):
        return "map_lookup"
    if isinstance(outcome, QuestionPlan):
        return "ask_user"
    return "final"


async def run_graph(
    address: str,
    *,
    resolve: Callable[[str], Awaitable[Site]],
    agents: workflow.AgentRegistry,
    radius_m: int,
    request_id: str,
    generate: GenerateDecision | None = None,
    agent_timeout: float = 180.0,
    supplements: list[tools.SupplementTool] | None = None,
    allow_questions: bool = False,
    map_lookup: tools.MapLookup | None = None,
    hooks: RunHooks | None = None,
    mode: AnalysisMode = "single_decision",
    generate_specialists: dict[SpecialistId, GenerateSpecialist] | None = None,
    resume_state: GraphState | None = None,
    user_answers: list[LandlordAnswer] | None = None,
    evaluators_enabled: bool = False,
    generate_evaluators: dict[EvaluatorId, GenerateEvaluation] | None = None,
    retry_only: bool = False,
) -> DecisionResult | WaitingForInput:
    """외부 호출 전에 실행 구성을 검증하고 고정 단계와 선택 분기를 실행합니다."""
    hooks = hooks or RunHooks()
    if evaluators_enabled and (
        not generate_evaluators
        or set(generate_evaluators) != set(EVALUATOR_IDS)
        or not all(callable(fn) for fn in generate_evaluators.values())
    ):
        raise ValueError("평가자 네 명의 호출 함수를 등록해 주세요.")
    if mode not in {"single_decision", "multi_agent"}:
        raise ValueError("지원하지 않는 분석 모드입니다.")
    if (
        mode == "multi_agent"
        and not retry_only
        and (
            not generate_specialists
            or not set(AGENT_IDS) <= set(generate_specialists)
            or (map_lookup is not None and "map_analysis" not in generate_specialists)
            or not all(callable(fn) for fn in generate_specialists.values())
        )
    ):
        raise ValueError("전문가 호출 함수를 등록해 주세요.")
    if resume_state is not None and (
        (mode != "multi_agent" and not retry_only)
        or allow_questions
        or resume_state["task"].request_id != request_id
    ):
        raise ValueError("재개 요청의 모드·식별자·질문 설정이 올바르지 않습니다.")
    if retry_only and (resume_state is None or allow_questions or supplements or map_lookup):
        raise ValueError("판정 재시도는 저장된 자료만 사용합니다.")
    budget = current_scope()[0] or (
        LLMBudget(limit=EVALUATED_MAX_CALLS if evaluators_enabled else MAX_CALLS)
        if mode == "multi_agent" or evaluators_enabled
        else None
    )
    supplements = list(supplements or [])
    validate_tools(supplements)
    validate_radius(radius_m)
    validate_timeout(agent_timeout)
    if not isinstance(address, str) or not address.strip():
        raise ValueError("주소가 비어 있습니다.")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("요청 ID가 비어 있습니다.")
    if set(agents) != set(AGENT_IDS) or not all(callable(a) for a in agents.values()):
        raise ValueError("세 분석 에이전트의 호출 함수를 등록해 주세요.")
    if not callable(resolve) or (generate is not None and not callable(generate)):
        raise ValueError("주소 변환·최종판단은 호출 가능한 함수여야 합니다.")
    if map_lookup is not None and not callable(map_lookup):
        raise ValueError("지도 조회 함수가 필요합니다.")
    if type(allow_questions) is not bool:
        raise ValueError("질문 허용 여부는 참 또는 거짓이어야 합니다.")
    if allow_questions and hooks.on_questions is None:
        raise ValueError("질문을 저장할 수 없는 실행입니다.")
    if any(
        (hook := getattr(hooks, field.name)) is not None and not callable(hook)
        for field in fields(hooks)
    ):
        raise ValueError("저장·관찰 콜백은 호출 가능한 함수여야 합니다.")

    async def step(stage: str, event: str, **detail) -> None:
        if hooks.on_step is not None:
            await hooks.on_step(stage, event, detail)

    async def prepare_address(state: GraphState) -> GraphState:
        await step("address", "started")
        task = await workflow.prepare_task(
            address,
            resolve=resolve,
            radius_m=radius_m,
            request_id=request_id,
        )
        if hooks.on_task_prepared is not None:
            await hooks.on_task_prepared(task)
        await step("address", "completed", road_address=task.site.road_address)
        return {"task": task}

    async def run_analyses(state: GraphState) -> GraphState:
        for agent_id in agents:
            await step(agent_id, "started")

        async def completed(analysis: AgentAnalysis) -> None:
            if hooks.on_analysis_completed is not None:
                await hooks.on_analysis_completed(analysis)
            await step(analysis.agent_id, "completed", status=analysis.status)

        analyses = await workflow.run_agents(
            state["task"],
            agents,
            on_analysis_completed=completed,
            agent_timeout=agent_timeout,
        )
        return {"analyses": analyses}

    async def evaluate_decision(state: GraphState) -> GraphState:
        phase = (
            {"phase": "final" if "evaluations" in state else "draft"} if evaluators_enabled else {}
        )
        await step("decision", "started", **phase)
        result = await _evaluate(state)
        await step("decision", "completed", action=action_of(result["outcome"]), **phase)
        if (
            evaluators_enabled
            and "evaluations" not in state
            and isinstance(result["outcome"], DecisionResult)
        ):
            reason = (
                "no_data"
                if result["outcome"].status == "no_data"
                else "budget"
                if budget is not None and budget.open_calls < 4
                else None
            )
            if reason:
                await step("evaluate", "completed", skipped=reason)
                result["final_call"] = False
        return result

    def remaining_rounds(state):
        ceiling = state.get("evaluation_start_round", 0) + 4 if "evaluations" in state else 2
        return max(0, ceiling - state["consult_round"])

    def expert_calls(state):
        return (
            budget.open_calls
            - (EVALUATOR_RESERVE if evaluators_enabled and "evaluations" not in state else 0)
            if budget
            else CONSULT_STEPS
        )

    async def judge(state, request, **kwargs):
        entries: list[EvaluationLogEntry] = []
        extra = {}
        if "evaluations" in state:
            extra = {
                "evaluation": decision_evaluation(state["draft"], state["evaluations"]),
                "evaluation_log": entries,
            }
        outcome = await decision.evaluate(request, **kwargs, **extra)
        if (
            "evaluations" in state
            and isinstance(outcome, DecisionResult)
            and hooks.on_evaluation_log
        ):
            await hooks.on_evaluation_log(entries)
        return outcome

    async def _evaluate(state: GraphState) -> GraphState:
        task = state["task"]
        request = DecisionRequest(
            request_id=task.request_id,
            address=task.site.input_address,
            analyses=state["analyses"],
            map_observation=state.get("map_observation"),
        )
        questions_allowed = allow_questions and (not evaluators_enabled or "evaluations" in state)
        if mode == "multi_agent":
            context = state["context"]
            request.map_observation = context.get("map_observation")
            specialists = [*AGENT_IDS, *(["map_analysis"] if map_lookup else [])]
            if (
                retry_only
                or not remaining_rounds(state)
                or budget is not None
                and expert_calls(state) < 3
            ):
                specialists = []
            outcome = await judge(
                state,
                request,
                generate=generate,
                site=task.site,
                user_answers=user_answers,
                question_fields=list(QUESTION_FIELDS)
                if questions_allowed and (budget is None or budget.open_calls > 0)
                else None,
                feedback=context.get("feedback"),
                supplement_context=context.get("supplement_context"),
                deliberation={
                    "briefs": state["briefs"],
                    "answers": state["answers"],
                    "specialists": specialists,
                    "consult_round": state["consult_round"],
                    **(
                        {"remaining_consult_rounds": remaining_rounds(state)}
                        if evaluators_enabled
                        else {}
                    ),
                },
            )
            return {"outcome": outcome}
        if state["supplement_done"]:
            outcome = await judge(
                state,
                request,
                generate=generate,
                feedback=state["feedback"],
                user_answers=user_answers,
                supplement_context=state["supplement_context"],
                question_fields=list(QUESTION_FIELDS) if questions_allowed else None,
                site=task.site if allow_questions else None,
                allow_map_lookup=map_lookup is not None and not state["map_done"],
            )
            if isinstance(outcome, SupplementPlan):
                raise ValueError("보완 라운드를 추가 실행할 수 없습니다.")
            return {"outcome": outcome}
        sources = {item.agent_id: item for item in state["analyses"]}
        operations = [
            tool.operation
            for tool in supplements
            if tool.eligible(
                task.model_copy(deep=True),
                sources[tool.operation.agent_id].model_copy(deep=True),
            )
        ]
        outcome = await judge(
            state,
            request,
            generate=generate,
            operations=operations,
            user_answers=user_answers,
            question_fields=list(QUESTION_FIELDS) if questions_allowed else None,
            site=task.site if allow_questions else None,
            allow_map_lookup=map_lookup is not None and not state["map_done"],
        )
        return {"outcome": outcome, "operations": operations}

    async def execute_map(state: GraphState) -> GraphState:
        plan = state["outcome"]
        task = state["task"]
        if state["map_done"] or map_lookup is None or not isinstance(plan, MapLookupPlan):
            raise ValueError("지도 조회를 추가 실행할 수 없습니다.")
        plan = MapLookupPlan.model_validate(plan)
        if hooks.on_map_requested is not None:
            await hooks.on_map_requested(task.model_copy(deep=True), plan.model_copy(deep=True))
        await step("map", "started", queries=len(plan.unique_queries()))
        raw = await execute_map_lookup(task, plan, map_lookup, agent_timeout)
        observed = MapObservation.model_validate(raw)
        if (
            observed.request_id != task.request_id
            or observed.site != task.site
            or observed.radius_m != task.radius_m
            or [q.request for q in observed.data.queries.values()] != plan.unique_queries()
        ):
            raise ValueError("지도 요청과 관측의 식별자·위치·검색 대상이 다릅니다.")
        if hooks.on_map_completed is not None:
            await hooks.on_map_completed(observed.model_copy(deep=True))
        await step("map", "completed", status=observed.status)
        return {"map_done": True, "map_observation": observed}

    async def ask_user(state: GraphState) -> GraphState:
        plan = state["outcome"]
        if not allow_questions or hooks.on_questions is None or not isinstance(plan, QuestionPlan):
            raise ValueError("질문을 저장할 수 없는 실행입니다.")
        waiting = WaitingForInput(
            request_id=state["task"].request_id,
            question_set_id=uuid.uuid4().hex,
            questions=plan.questions,
        )
        await step("questions", "waiting", count=len(plan.questions))
        await hooks.on_questions(
            state["task"],
            waiting,
            state["supplement_done"],
            state["context"].get("feedback", [])
            if mode == "multi_agent"
            else state.get("feedback", []),
        )
        return {"outcome": waiting}

    async def supplement_node(state: GraphState) -> GraphState:
        plan = state["outcome"]
        if state["supplement_done"] or not isinstance(plan, SupplementPlan):
            raise ValueError("현재 단계에서는 보완을 실행할 수 없습니다.")
        # 판단에 실제 제시한 작업만 허용하고 실행 직전에 조건을 다시 확인합니다.
        offered = {(op.agent_id, op.operation) for op in state["operations"]}
        await step("supplement", "started", agents=sorted({r.agent_id for r in plan.requests}))
        updated, feedback, context = await execute_supplement(
            state["task"],
            state["analyses"],
            plan,
            tools=[
                tool
                for tool in supplements
                if (tool.operation.agent_id, tool.operation.operation) in offered
            ],
            on_event=hooks.on_supplement,
            operation_timeout=agent_timeout,
        )
        await step("supplement", "completed")
        return {
            "analyses": updated,
            "feedback": feedback,
            "supplement_context": context,
            "supplement_done": True,
        }

    async def collect(coroutines):
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return results

    def registered(state, agent_id, query=None):
        return build_specialist_tools(
            state["task"],
            agent_id,
            analyses=state["analyses"],
            supplements=supplements,
            map_lookup=map_lookup,
            hooks=hooks,
            context=state["context"],
            query=query,
            operation_timeout=agent_timeout,
        )

    def current_data(state, agent_id):
        if agent_id == "map_analysis":
            observation = state["context"].get("map_observation")
            return observation.data.model_dump(mode="json") if observation else {}
        return next(a.data for a in state["analyses"] if a.agent_id == agent_id)

    async def write_briefs(state: GraphState) -> GraphState:
        async def one(source):
            assert generate_specialists is not None
            await step("brief." + source.agent_id, "started")
            brief = await write_brief(
                state["task"],
                source,
                generate=generate_specialists[source.agent_id],
                tools=registered(state, source.agent_id),
                get_data=lambda: current_data(state, source.agent_id),
                max_steps=BRIEF_STEPS,
            )
            if hooks.on_brief:
                await hooks.on_brief(brief.model_copy(deep=True))
            await step(
                "brief." + source.agent_id,
                "completed",
                source=brief.source,
                findings=len(brief.findings),
            )
            return brief

        briefs = await collect(one(source) for source in list(state["analyses"]))
        return {"briefs": briefs, "analyses": state["analyses"], "context": state["context"]}

    async def consult(state: GraphState) -> GraphState:
        plan = state["outcome"]
        if not isinstance(plan, ConsultPlan) or not remaining_rounds(state):
            raise ValueError("전문가 되묻기 한도를 초과했습니다.")
        round_number = state["consult_round"] + 1
        # 전문가가 병렬로 예산을 나눠 쓰므로 시작 전에 몫을 정해 finish 차례를 보장합니다.
        share = expert_calls(state) // len(plan.queries) if budget is not None else CONSULT_STEPS

        async def one(query):
            assert generate_specialists is not None
            previous = next(
                (
                    a.model_copy(deep=True)
                    for a in state["analyses"]
                    if a.agent_id == query.agent_id
                ),
                None,
            )
            old_map = state["context"].get("map_observation")
            await step(
                "consult." + query.agent_id,
                "started",
                round=round_number,
                question=query.question[:300],
            )
            answer = await answer_query(
                state["task"],
                query,
                round_number,
                analysis=previous,
                observation=old_map,
                generate=generate_specialists[query.agent_id],
                tools=registered(state, query.agent_id, query),
                get_data=lambda: current_data(state, query.agent_id),
                get_observation=lambda: state["context"].get("map_observation"),
                max_steps=consult_steps(query.agent_id, share),
            )
            current = next((a for a in state["analyses"] if a.agent_id == query.agent_id), None)
            if current is not None and current != previous:
                answer.analysis = current.model_copy(deep=True)
            if (
                query.agent_id == "map_analysis"
                and state["context"].get("map_observation") != old_map
            ):
                answer.map_observation = state["context"]["map_observation"].model_copy(deep=True)
            answer = SpecialistAnswer.model_validate(answer)
            if hooks.on_consult:
                await hooks.on_consult(answer.model_copy(deep=True))
            await step(
                "consult." + query.agent_id,
                "completed",
                round=round_number,
                status=answer.status,
                tools=[call.tool for call in answer.tool_calls],
            )
            return answer

        answers = await collect(one(query) for query in plan.queries)
        return {
            "answers": [*state["answers"], *answers],
            "consult_round": round_number,
            "analyses": state["analyses"],
            "context": state["context"],
        }

    async def evaluate_draft_node(state: GraphState) -> GraphState:
        draft = state["outcome"]
        assert isinstance(draft, DecisionResult)
        context = state["context"] if mode == "multi_agent" else state
        request = DecisionRequest(
            request_id=request_id,
            address=address,
            analyses=state["analyses"],
            map_observation=context.get("map_observation"),
        )
        allowed: list[EvaluationRequest] = ["none"]
        map_queries = state["context"].get("map_queries") if mode == "multi_agent" else None
        if map_lookup and not (map_queries or context.get("map_observation") or state["map_done"]):
            allowed.append("map_lookup")
        if supplements and not (state["supplement_done"] or context.get("supplement_context")):
            allowed.append("supplement")
        if mode == "multi_agent" and not retry_only:
            allowed.append("ask_specialists")
        if allow_questions:
            allowed.append("ask_user")

        async def one(role):
            assert generate_evaluators is not None
            await step("evaluate." + role, "started")
            result = await evaluate_draft(
                role,
                request,
                draft,
                generate=generate_evaluators[role],
                allowed=allowed,
                timeout=agent_timeout,
            )
            await step(
                "evaluate." + role,
                "completed",
                source=result.source,
                verdict=result.verdict,
                comments=len(result.comments),
            )
            return result

        evaluations = await collect(one(role) for role in EVALUATOR_IDS)
        if hooks.on_evaluation:
            await hooks.on_evaluation(draft, evaluations)
        successful = [e for e in evaluations if e.source == "model"]
        reason = (
            "all_failed"
            if not successful
            else "no_comments"
            if all(e.verdict == "agree" and not e.comments for e in successful)
            else "comments"
        )
        final_call = reason == "comments"
        await step("evaluate", "completed", final_call=final_call, reason=reason)
        return {
            "draft": draft,
            "evaluations": evaluations,
            "evaluation_start_round": state["consult_round"],
            "final_call": final_call,
        }

    def route(state):
        outcome = state["outcome"]
        if isinstance(outcome, ConsultPlan):
            return "consult"
        if isinstance(outcome, MapLookupPlan):
            return "map"
        if isinstance(outcome, SupplementPlan):
            return "supplement"
        if isinstance(outcome, QuestionPlan):
            return "question"
        if evaluators_enabled and "evaluations" not in state and state.get("final_call", True):
            return "evaluate"
        return "final"

    builder = StateGraph(GraphState)
    builder.add_node("prepare_address", prepare_address)
    builder.add_node("run_analyses", run_analyses)
    builder.add_node("evaluate_decision", evaluate_decision)
    builder.add_node("execute_supplement", supplement_node)
    builder.add_node("ask_user", ask_user)
    builder.add_node("execute_map", execute_map)
    builder.add_edge(START, "evaluate_decision" if resume_state is not None else "prepare_address")
    builder.add_edge("prepare_address", "run_analyses")
    if mode == "multi_agent":
        builder.add_node("write_briefs", write_briefs)
        builder.add_node("consult", consult)
        builder.add_edge("run_analyses", "write_briefs")
        builder.add_edge("write_briefs", "evaluate_decision")
        builder.add_edge("consult", "evaluate_decision")
    else:
        builder.add_edge("run_analyses", "evaluate_decision")
    builder.add_conditional_edges(
        "evaluate_decision",
        route,
        {
            "map": "execute_map",
            "supplement": "execute_supplement",
            "question": "ask_user",
            "final": END,
            **({"evaluate": "evaluate_draft"} if evaluators_enabled else {}),
            **({"consult": "consult"} if mode == "multi_agent" else {}),
        },
    )
    if evaluators_enabled:
        builder.add_node("evaluate_draft", evaluate_draft_node)
        builder.add_conditional_edges(
            "evaluate_draft",
            lambda state: "final" if state["final_call"] else "end",
            {"final": "evaluate_decision", "end": END},
        )
    builder.add_edge("execute_supplement", "evaluate_decision")
    builder.add_edge("execute_map", "evaluate_decision")
    builder.add_edge("ask_user", END)
    graph = builder.compile()
    initial: GraphState = {
        "supplement_done": False,
        "map_done": False,
        "briefs": [],
        "answers": [],
        "consult_round": 0,
        "context": {},
    }
    if resume_state is not None:
        initial.update(resume_state)
    # 주소·분석 자료는 기존 로컬 trace에만 남기고 외부 자동 추적은 사용하지 않습니다.
    with tracing_context(enabled=False), llm_scope(budget, "decision", final=True):
        final = await graph.ainvoke(initial, config={"recursion_limit": 32})
    result = final["outcome"]
    if not isinstance(result, (DecisionResult, WaitingForInput)):
        raise ValueError("그래프가 최종판단 결과를 반환하지 않았습니다.")
    return result
