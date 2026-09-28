"""기존 도구 계약을 유지하며 판단·보완 분기를 그래프로 실행합니다."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from importlib.resources import files
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from openai.types.chat import ChatCompletionMessage

from app.agents.decision import agent as decision
from app.agents.decision.agent import GenerateDecision
from app.schemas import (
    QUESTION_FIELDS,
    AgentAnalysis,
    AnalysisTask,
    DecisionRequest,
    DecisionResult,
    LandlordAnswer,
    MapLookupPlan,
    MapObservation,
    QuestionPlan,
    Site,
    SupplementEvent,
    SupplementOperation,
    SupplementPlan,
    WaitingForInput,
)

from . import llm, tools, workflow
from .supplement import OnSupplement, execute_supplement

NextNode = Literal["choose_action", "prepare_address", "run_analyses", "evaluate_decision"]


class GraphState(TypedDict, total=False):
    """요청별 데이터만 보관하며 실행 함수와 비밀키는 포함하지 않습니다."""

    messages: list[Any]
    action_calls: int
    next_node: NextNode
    call_id: str
    task: AnalysisTask
    analyses: list[AgentAnalysis]
    outcome: DecisionResult | SupplementPlan | QuestionPlan | WaitingForInput | MapLookupPlan
    map_done: bool
    map_observation: MapObservation
    operations: list[SupplementOperation]
    supplement_done: bool
    feedback: list[str]
    supplement_context: list[SupplementEvent]


def _observation(messages: list[Any], call_id: str, value: dict[str, Any]) -> list[Any]:
    return [
        *messages,
        {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(value, ensure_ascii=False, allow_nan=False),
        },
    ]


async def run_graph(
    address: str,
    *,
    resolve: Callable[[str], Awaitable[Site]],
    agents: workflow.AgentRegistry,
    radius_m: int,
    request_id: str,
    generate_action: workflow.GenerateAction | None,
    generate: GenerateDecision | None,
    on_task_prepared: Callable[[AnalysisTask], Awaitable[None]] | None,
    on_analysis_completed: Callable[[AgentAnalysis], Awaitable[None]] | None,
    agent_timeout: float,
    supplements: list[tools.SupplementTool],
    on_supplement: OnSupplement | None,
    allow_questions: bool = False,
    map_lookup: tools.MapLookup | None = None,
    on_map_requested: tools.OnMapRequested | None = None,
    on_map_completed: tools.OnMapCompleted | None = None,
    on_questions: Callable[[AnalysisTask, WaitingForInput, bool, list[str]], Awaitable[None]]
    | None = None,
) -> DecisionResult | WaitingForInput:
    """검증된 입력으로 실행합니다. 외부 진입점은 workflow.run_react입니다."""
    choose = generate_action or llm.generate_action

    async def choose_action(state: GraphState) -> GraphState:
        if state["action_calls"] >= 6:
            raise RuntimeError("오케스트레이터의 최대 모델 호출 횟수 6회를 초과했습니다.")
        message = ChatCompletionMessage.model_validate(
            await choose(state["messages"], tools.TOOL_DEFINITIONS)
        )
        if message.refusal or not message.tool_calls or len(message.tool_calls) != 1:
            raise RuntimeError("모델은 한 번에 하나의 도구를 호출해야 합니다.")
        call = message.tool_calls[0]
        if call.type != "function":
            raise RuntimeError("지원하지 않는 도구 호출 형식입니다.")
        messages = [
            *state["messages"],
            message.model_dump(
                include={"role", "content", "tool_calls"},
                exclude_none=True,
            ),
        ]
        expected = (
            "prepare_address"
            if "task" not in state
            else "run_analyses"
            if "analyses" not in state
            else "make_decision"
        )
        try:
            arguments = json.loads(call.function.arguments)
        except (ValueError, TypeError):
            arguments = None
        route: NextNode
        if arguments != {} or call.function.name != expected:
            messages = _observation(
                messages,
                call.id,
                {
                    "status": "error",
                    "message": f"빈 인자로 {expected}를 호출하세요.",
                },
            )
            route = "choose_action"
        elif expected == "prepare_address":
            route = "prepare_address"
        elif expected == "run_analyses":
            route = "run_analyses"
        else:
            route = "evaluate_decision"
        return {
            "messages": messages,
            "action_calls": state["action_calls"] + 1,
            "call_id": call.id,
            "next_node": route,
        }

    async def prepare_address(state: GraphState) -> GraphState:
        task = await workflow.prepare_task(
            address,
            resolve=resolve,
            radius_m=radius_m,
            request_id=request_id,
        )
        if on_task_prepared is not None:
            await on_task_prepared(task)
        return {
            "task": task,
            "messages": _observation(
                state["messages"],
                state["call_id"],
                {"status": "ok", "task": task.model_dump(mode="json")},
            ),
        }

    async def run_analyses(state: GraphState) -> GraphState:
        analyses = await workflow.run_agents(
            state["task"],
            agents,
            on_analysis_completed=on_analysis_completed,
            agent_timeout=agent_timeout,
        )
        return {
            "analyses": analyses,
            "messages": _observation(
                state["messages"],
                state["call_id"],
                {
                    "status": "ok",
                    "analyses": [
                        item.model_dump(mode="json", include={"agent_id", "status", "scope"})
                        for item in analyses
                    ],
                },
            ),
        }

    async def evaluate_decision(state: GraphState) -> GraphState:
        task = state["task"]
        request = DecisionRequest(
            request_id=task.request_id,
            address=task.site.input_address,
            analyses=state["analyses"],
            map_observation=state.get("map_observation"),
        )
        if not supplements and not allow_questions and map_lookup is None:
            return {"outcome": await decision.analyze(request, generate=generate)}
        if state["supplement_done"]:
            outcome = await decision.evaluate(
                request,
                generate=generate,
                feedback=state["feedback"],
                supplement_context=state["supplement_context"],
                question_fields=list(QUESTION_FIELDS) if allow_questions else None,
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
        outcome = await decision.evaluate(
            request,
            generate=generate,
            operations=operations,
            question_fields=list(QUESTION_FIELDS) if allow_questions else None,
            site=task.site if allow_questions else None,
            allow_map_lookup=map_lookup is not None and not state["map_done"],
        )
        return {"outcome": outcome, "operations": operations}

    async def execute_map(state: GraphState) -> GraphState:
        from app.agents.map_analysis.agent import failed_observation

        plan = state["outcome"]
        task = state["task"]
        if state["map_done"] or map_lookup is None or not isinstance(plan, MapLookupPlan):
            raise ValueError("지도 조회를 추가 실행할 수 없습니다.")
        plan = MapLookupPlan.model_validate(plan)
        if on_map_requested is not None:
            await on_map_requested(task.model_copy(deep=True), plan.model_copy(deep=True))
        try:
            async with asyncio.timeout(agent_timeout):
                raw = await map_lookup(task.model_copy(deep=True), plan.model_copy(deep=True))
        except TimeoutError:
            raw = failed_observation(task, plan, "MAP_TIMEOUT")
        except (ValueError, TypeError):
            raise
        except Exception:
            raw = failed_observation(task, plan, "MAP_FAILED")
        observed = MapObservation.model_validate(raw)
        if (
            observed.request_id != task.request_id
            or observed.site != task.site
            or observed.radius_m != task.radius_m
            or [q.request for q in observed.data.queries.values()] != plan.unique_queries()
        ):
            raise ValueError("지도 요청과 관측의 식별자·위치·검색 대상이 다릅니다.")
        if on_map_completed is not None:
            await on_map_completed(observed.model_copy(deep=True))
        return {"map_done": True, "map_observation": observed}

    async def ask_user(state: GraphState) -> GraphState:
        plan = state["outcome"]
        if not allow_questions or on_questions is None or not isinstance(plan, QuestionPlan):
            raise ValueError("질문을 저장할 수 없는 실행입니다.")
        waiting = WaitingForInput(
            request_id=state["task"].request_id,
            question_set_id=uuid.uuid4().hex,
            questions=plan.questions,
        )
        await on_questions(
            state["task"], waiting, state["supplement_done"], state.get("feedback", [])
        )
        return {"outcome": waiting}

    async def supplement_node(state: GraphState) -> GraphState:
        plan = state["outcome"]
        if state["supplement_done"] or not isinstance(plan, SupplementPlan):
            raise ValueError("현재 단계에서는 보완을 실행할 수 없습니다.")
        # 판단에 실제 제시한 작업만 허용하고 실행 직전에 조건을 다시 확인합니다.
        offered = {(op.agent_id, op.operation) for op in state["operations"]}
        updated, feedback, context = await execute_supplement(
            state["task"],
            state["analyses"],
            plan,
            tools=[
                tool
                for tool in supplements
                if (tool.operation.agent_id, tool.operation.operation) in offered
            ],
            on_event=on_supplement,
            operation_timeout=agent_timeout,
        )
        return {
            "analyses": updated,
            "feedback": feedback,
            "supplement_context": context,
            "supplement_done": True,
        }

    builder = StateGraph(GraphState)
    builder.add_node("choose_action", choose_action)
    builder.add_node("prepare_address", prepare_address)
    builder.add_node("run_analyses", run_analyses)
    builder.add_node("evaluate_decision", evaluate_decision)
    builder.add_node("execute_supplement", supplement_node)
    builder.add_node("ask_user", ask_user)
    builder.add_node("execute_map", execute_map)
    builder.add_edge(START, "choose_action")
    builder.add_conditional_edges(
        "choose_action",
        lambda state: state["next_node"],
        {
            name: name
            for name in ("choose_action", "prepare_address", "run_analyses", "evaluate_decision")
        },
    )
    builder.add_edge("prepare_address", "choose_action")
    builder.add_edge("run_analyses", "choose_action")
    builder.add_conditional_edges(
        "evaluate_decision",
        lambda state: (
            "map"
            if isinstance(state["outcome"], MapLookupPlan)
            else "supplement"
            if isinstance(state["outcome"], SupplementPlan)
            else "question"
            if isinstance(state["outcome"], QuestionPlan)
            else "final"
        ),
        {
            "map": "execute_map",
            "supplement": "execute_supplement",
            "question": "ask_user",
            "final": END,
        },
    )
    builder.add_edge("execute_supplement", "evaluate_decision")
    builder.add_edge("execute_map", "evaluate_decision")
    builder.add_edge("ask_user", END)
    graph = builder.compile()
    initial: GraphState = {
        "messages": [
            {
                "role": "system",
                "content": files(__package__).joinpath("prompt.md").read_text("utf-8"),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"address": address, "radius_m": radius_m},
                    ensure_ascii=False,
                ),
            },
        ],
        "action_calls": 0,
        "supplement_done": False,
        "map_done": False,
    }
    # 주소·분석 자료는 기존 로컬 trace에만 남기고 외부 자동 추적은 사용하지 않습니다.
    with tracing_context(enabled=False):
        final = await graph.ainvoke(initial, config={"recursion_limit": 32})
    result = final["outcome"]
    if not isinstance(result, (DecisionResult, WaitingForInput)):
        raise ValueError("그래프가 최종판단 결과를 반환하지 않았습니다.")
    return result


async def resume_graph(
    request: DecisionRequest,
    *,
    site: Site,
    answers: list[LandlordAnswer],
    feedback: list[str],
    supplement_context: list[SupplementEvent],
    generate: GenerateDecision | None = None,
) -> DecisionResult:
    """저장된 분석으로 판단만 실행합니다. 주소·분석·보완 노드는 등록하지 않습니다."""
    request = DecisionRequest.model_validate(request)

    async def evaluate_decision(state: GraphState) -> GraphState:
        outcome = await decision.evaluate(
            request,
            site=site,
            user_answers=answers,
            feedback=feedback,
            supplement_context=supplement_context,
            generate=generate,
        )
        if not isinstance(outcome, DecisionResult):
            raise ValueError("답변 후에는 최종판단만 허용합니다.")
        return {"outcome": outcome}

    builder = StateGraph(GraphState)
    builder.add_node("evaluate_decision", evaluate_decision)
    builder.add_edge(START, "evaluate_decision")
    builder.add_edge("evaluate_decision", END)
    with tracing_context(enabled=False):
        result = await builder.compile().ainvoke({})
    return result["outcome"]
