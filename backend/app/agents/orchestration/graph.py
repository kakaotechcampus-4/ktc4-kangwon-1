"""의존성과 노드를 연결해 분석 그래프를 실행합니다."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from app.agents.decision.agent import GenerateDecision
from app.agents.evaluators.agent import GenerateEvaluation
from app.agents.orchestration import tools, workflow
from app.agents.specialists.agent import GenerateSpecialist
from app.llm.budget import EVALUATED_MAX_CALLS, MAX_CALLS, LLMBudget, current_scope, llm_scope
from app.schemas import (
    AnalysisMode,
    DecisionResult,
    EvaluatorId,
    LandlordAnswer,
    Site,
    SpecialistId,
    WaitingForInput,
)

from .constants import DEFAULT_AGENT_TIMEOUT, RECURSION_LIMIT
from .deps import GraphDeps
from .nodes.analysis import prepare_address, run_analyses
from .nodes.decision import evaluate_decision, route
from .nodes.deliberation import consult, write_briefs
from .nodes.deliberation import consult_steps as consult_steps
from .nodes.evaluation import evaluate_draft_node
from .nodes.tools import ask_user, execute_map, supplement_node
from .state import GraphState as GraphState
from .state import RunHooks as RunHooks
from .state import initial_state
from .state import normalize_resume_state as normalize_resume_state


def build_graph(deps: GraphDeps, *, resume: bool = False):
    builder = StateGraph(GraphState)
    builder.add_node("prepare_address", partial(prepare_address, deps=deps))
    builder.add_node("run_analyses", partial(run_analyses, deps=deps))
    builder.add_node("evaluate_decision", partial(evaluate_decision, deps=deps))
    builder.add_node("execute_supplement", partial(supplement_node, deps=deps))
    builder.add_node("ask_user", partial(ask_user, deps=deps))
    builder.add_node("execute_map", partial(execute_map, deps=deps))
    builder.add_edge(START, "evaluate_decision" if resume else "prepare_address")
    builder.add_edge("prepare_address", "run_analyses")
    if deps.mode == "multi_agent":
        builder.add_node("write_briefs", partial(write_briefs, deps=deps))
        builder.add_node("consult", partial(consult, deps=deps))
        builder.add_edge("run_analyses", "write_briefs")
        builder.add_edge("write_briefs", "evaluate_decision")
        builder.add_edge("consult", "evaluate_decision")
    else:
        builder.add_edge("run_analyses", "evaluate_decision")
    builder.add_conditional_edges(
        "evaluate_decision",
        partial(route, deps=deps),
        {
            "map": "execute_map",
            "supplement": "execute_supplement",
            "question": "ask_user",
            "final": END,
            **({"evaluate": "evaluate_draft"} if deps.evaluators_enabled else {}),
            **({"consult": "consult"} if deps.mode == "multi_agent" else {}),
        },
    )
    if deps.evaluators_enabled:
        builder.add_node("evaluate_draft", partial(evaluate_draft_node, deps=deps))
        builder.add_conditional_edges(
            "evaluate_draft",
            lambda state: "final" if state["final_call"] else "end",
            {"final": "evaluate_decision", "end": END},
        )
    builder.add_edge("execute_supplement", "evaluate_decision")
    builder.add_edge("execute_map", "evaluate_decision")
    builder.add_edge("ask_user", END)
    return builder.compile()


async def run_graph(
    address: str,
    *,
    resolve: Callable[[str], Awaitable[Site]],
    agents: workflow.AgentRegistry,
    radius_m: int,
    request_id: str,
    generate: GenerateDecision | None = None,
    agent_timeout: float = DEFAULT_AGENT_TIMEOUT,
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
    """의존성을 검증하고 고정 단계와 선택 분기를 실행합니다."""
    budget = current_scope()[0] or (
        LLMBudget(limit=EVALUATED_MAX_CALLS if evaluators_enabled else MAX_CALLS)
        if mode == "multi_agent" or evaluators_enabled
        else None
    )
    deps = GraphDeps(
        address=address,
        request_id=request_id,
        radius_m=radius_m,
        resolve=resolve,
        agents=agents,
        generate=generate,
        generate_specialists=generate_specialists,
        generate_evaluators=generate_evaluators,
        supplements=list(supplements or []),
        map_lookup=map_lookup,
        hooks=hooks or RunHooks(),
        budget=budget,
        agent_timeout=agent_timeout,
        mode=mode,
        allow_questions=allow_questions,
        evaluators_enabled=evaluators_enabled,
        retry_only=retry_only,
        user_answers=user_answers,
    )
    if resume_state is not None and (
        (mode != "multi_agent" and not retry_only)
        or allow_questions
        or resume_state["task"].request_id != request_id
    ):
        raise ValueError("재개 요청의 모드·식별자·질문 설정이 올바르지 않습니다.")
    if retry_only and (resume_state is None or allow_questions or supplements or map_lookup):
        raise ValueError("판정 재시도는 저장된 자료만 사용합니다.")
    initial = initial_state(resume_state, mode=mode)
    # 주소·분석 자료는 기존 로컬 trace에만 남기고 외부 자동 추적은 사용하지 않습니다.
    with tracing_context(enabled=False), llm_scope(budget, "decision", final=True):
        final = await build_graph(deps, resume=resume_state is not None).ainvoke(
            initial, config={"recursion_limit": RECURSION_LIMIT}
        )
    result = final["outcome"]
    if not isinstance(result, (DecisionResult, WaitingForInput)):
        raise ValueError("그래프가 최종판단 결과를 반환하지 않았습니다.")
    return result
