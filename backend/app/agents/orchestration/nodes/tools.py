"""지도·보완·임대인 질문 노드입니다."""

from __future__ import annotations

import uuid

from app.agents.orchestration.deps import GraphDeps
from app.agents.orchestration.map import execute_map_lookup
from app.agents.orchestration.state import GraphState, GraphUpdate
from app.agents.orchestration.supplement import execute_supplement
from app.schemas import (
    MapLookupPlan,
    MapObservation,
    QuestionPlan,
    SupplementPlan,
    WaitingForInput,
)


async def execute_map(state: GraphState, *, deps: GraphDeps) -> GraphUpdate:
    plan = state["outcome"]
    task = state["task"]
    if state["map_done"] or deps.map_lookup is None or not isinstance(plan, MapLookupPlan):
        raise ValueError("지도 조회를 추가 실행할 수 없습니다.")
    plan = MapLookupPlan.model_validate(plan)
    if deps.hooks.on_map_requested is not None:
        await deps.hooks.on_map_requested(task.model_copy(deep=True), plan.model_copy(deep=True))
    await deps.step("map", "started", queries=len(plan.unique_queries()))
    raw = await execute_map_lookup(task, plan, deps.map_lookup, deps.agent_timeout)
    observed = MapObservation.model_validate(raw)
    if (
        observed.request_id != task.request_id
        or observed.site != task.site
        or observed.radius_m != task.radius_m
        or [q.request for q in observed.data.queries.values()] != plan.unique_queries()
    ):
        raise ValueError("지도 요청과 관측의 식별자·위치·검색 대상이 다릅니다.")
    if deps.hooks.on_map_completed is not None:
        await deps.hooks.on_map_completed(observed.model_copy(deep=True))
    await deps.step("map", "completed", status=observed.status)
    return {"map_done": True, "map_observation": observed}


async def ask_user(state: GraphState, *, deps: GraphDeps) -> GraphUpdate:
    plan = state["outcome"]
    if (
        not deps.allow_questions
        or deps.hooks.on_questions is None
        or not isinstance(plan, QuestionPlan)
    ):
        raise ValueError("질문을 저장할 수 없는 실행입니다.")
    waiting = WaitingForInput(
        request_id=state["task"].request_id,
        question_set_id=uuid.uuid4().hex,
        questions=plan.questions,
    )
    await deps.step("questions", "waiting", count=len(plan.questions))
    await deps.hooks.on_questions(
        state["task"],
        waiting,
        state["supplement_done"],
        state.get("feedback", []),
    )
    return {"outcome": waiting}


async def supplement_node(state: GraphState, *, deps: GraphDeps) -> GraphUpdate:
    plan = state["outcome"]
    if state["supplement_done"] or not isinstance(plan, SupplementPlan):
        raise ValueError("현재 단계에서는 보완을 실행할 수 없습니다.")
    # 판단에 실제 제시한 작업만 허용하고 실행 직전에 조건을 다시 확인합니다.
    offered = {(op.agent_id, op.operation) for op in state["operations"]}
    await deps.step("supplement", "started", agents=sorted({r.agent_id for r in plan.requests}))
    updated, feedback, context = await execute_supplement(
        state["task"],
        state["analyses"],
        plan,
        tools=[
            tool
            for tool in deps.supplements
            if (tool.operation.agent_id, tool.operation.operation) in offered
        ],
        on_event=deps.hooks.on_supplement,
        operation_timeout=deps.agent_timeout,
    )
    await deps.step("supplement", "completed")
    return {
        "analyses": updated,
        "feedback": feedback,
        "supplement_context": context,
        "supplement_done": True,
    }
