"""브리핑과 전문가 되묻기 노드입니다."""

from __future__ import annotations

from app.agents.orchestration.constants import (
    BRIEF_STEPS,
    CONSULT_STEPS,
    QUESTION_SUMMARY_LENGTH,
)
from app.agents.orchestration.consult import merge_specialist_changes
from app.agents.orchestration.deps import GraphDeps
from app.agents.orchestration.state import GraphState, GraphUpdate
from app.agents.orchestration.workflow import collect
from app.agents.specialists.agent import answer_query, write_brief
from app.schemas import (
    ConsultPlan,
    SpecialistAnswer,
)

from .decision import remaining_rounds


def consult_steps(agent_id: str, share: int) -> int:
    """배정된 호출 몫 안에서 finish까지 끝낼 수 있는 차례 수입니다."""
    if agent_id == "map_analysis":
        # 지도 검색 한 번은 업종 매핑 모델 호출을 한 번 더 쓸 수 있습니다.
        share = 1 + (share - 1) // 2
    return max(1, min(CONSULT_STEPS, share))


def current_data(state, agent_id, changes):
    if agent_id == "map_analysis":
        observation = changes.get("map_observation", state.get("map_observation"))
        return observation.data.model_dump(mode="json") if observation else {}
    changed = changes.get("analysis")
    return (
        changed.data
        if changed is not None
        else next(a.data for a in state["analyses"] if a.agent_id == agent_id)
    )


async def write_briefs(state: GraphState, *, deps: GraphDeps) -> GraphUpdate:
    async def one(source):
        assert deps.generate_specialists is not None
        await deps.step("brief." + source.agent_id, "started")
        tools, changes = deps.registered(state, source.agent_id)
        brief = await write_brief(
            state["task"],
            source,
            generate=deps.generate_specialists[source.agent_id],
            tools=tools,
            get_data=lambda: current_data(state, source.agent_id, changes),
            max_steps=BRIEF_STEPS,
        )
        if deps.hooks.on_brief:
            await deps.hooks.on_brief(brief.model_copy(deep=True))
        await deps.step(
            "brief." + source.agent_id,
            "completed",
            source=brief.source,
            findings=len(brief.findings),
        )
        return brief, changes

    results = await collect(one(source) for source in state["analyses"])
    return {
        "briefs": [brief for brief, _ in results],
        **merge_specialist_changes(state, [changes for _, changes in results]),
    }


async def consult(state: GraphState, *, deps: GraphDeps) -> GraphUpdate:
    plan = state["outcome"]
    if not isinstance(plan, ConsultPlan) or not remaining_rounds(state):
        raise ValueError("전문가 되묻기 한도를 초과했습니다.")
    round_number = state["consult_round"] + 1
    # 전문가가 병렬로 예산을 나눠 쓰므로 시작 전에 몫을 정해 finish 차례를 보장합니다.
    share = (
        deps.expert_calls(state) // len(plan.queries) if deps.budget is not None else CONSULT_STEPS
    )

    async def one(query):
        assert deps.generate_specialists is not None
        previous = next(
            (a.model_copy(deep=True) for a in state["analyses"] if a.agent_id == query.agent_id),
            None,
        )
        old_map = state.get("map_observation")
        tools, changes = deps.registered(state, query.agent_id, query)
        await deps.step(
            "consult." + query.agent_id,
            "started",
            round=round_number,
            question=query.question[:QUESTION_SUMMARY_LENGTH],
        )
        answer = await answer_query(
            state["task"],
            query,
            round_number,
            analysis=previous,
            observation=old_map,
            generate=deps.generate_specialists[query.agent_id],
            tools=tools,
            get_data=lambda: current_data(state, query.agent_id, changes),
            get_observation=lambda: changes.get("map_observation", old_map),
            max_steps=consult_steps(query.agent_id, share),
        )
        current = changes.get("analysis", previous)
        if current is not None and current != previous:
            answer.analysis = current.model_copy(deep=True)
        if query.agent_id == "map_analysis" and changes.get("map_observation", old_map) != old_map:
            answer.map_observation = changes["map_observation"].model_copy(deep=True)
        answer = SpecialistAnswer.model_validate(answer)
        if deps.hooks.on_consult:
            await deps.hooks.on_consult(answer.model_copy(deep=True))
        await deps.step(
            "consult." + query.agent_id,
            "completed",
            round=round_number,
            status=answer.status,
            tools=[call.tool for call in answer.tool_calls],
        )
        return answer, changes

    results = await collect(one(query) for query in plan.queries)
    return {
        "answers": [*state["answers"], *(answer for answer, _ in results)],
        "consult_round": round_number,
        **merge_specialist_changes(state, [changes for _, changes in results]),
    }
