"""주소와 병렬 분석 노드입니다."""

from __future__ import annotations

from app.agents.orchestration import workflow
from app.agents.orchestration.deps import GraphDeps
from app.agents.orchestration.state import GraphState, GraphUpdate
from app.schemas import (
    AgentAnalysis,
)


async def prepare_address(state: GraphState, *, deps: GraphDeps) -> GraphUpdate:
    await deps.step("address", "started")
    task = await workflow.prepare_task(
        deps.address,
        resolve=deps.resolve,
        radius_m=deps.radius_m,
        request_id=deps.request_id,
    )
    if deps.hooks.on_task_prepared is not None:
        await deps.hooks.on_task_prepared(task)
    await deps.step("address", "completed", road_address=task.site.road_address)
    return {"task": task}


async def run_analyses(state: GraphState, *, deps: GraphDeps) -> GraphUpdate:
    for agent_id in deps.agents:
        await deps.step(agent_id, "started")

    async def completed(analysis: AgentAnalysis) -> None:
        if deps.hooks.on_analysis_completed is not None:
            await deps.hooks.on_analysis_completed(analysis)
        await deps.step(analysis.agent_id, "completed", status=analysis.status)

    analyses = await workflow.run_agents(
        state["task"],
        deps.agents,
        on_analysis_completed=completed,
        agent_timeout=deps.agent_timeout,
    )
    return {"analyses": analyses}
