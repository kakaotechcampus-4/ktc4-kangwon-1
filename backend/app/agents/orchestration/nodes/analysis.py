"""주소와 병렬 분석 노드입니다."""

from __future__ import annotations

from app.agents.orchestration import workflow
from app.agents.orchestration.deps import GraphDeps
from app.agents.orchestration.state import GraphState, GraphUpdate
from app.education_zone import EducationZoneScan, scan_site
from app.schemas import (
    AgentAnalysis,
    Site,
)


async def _scan_zones(site: Site, *, deps: GraphDeps) -> EducationZoneScan | None:
    """교육환경보호구역을 한 번 조회합니다. 실패해도 분석은 계속합니다."""
    if deps.find_zones is None:
        return None
    await deps.step("education_zone", "started")
    scan = await scan_site(site, deps.find_zones)
    assert scan is not None
    await deps.step("education_zone", "completed", status=scan.status, zones=len(scan.zones))
    return scan


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
    zones = await _scan_zones(task.site, deps=deps)
    return {"task": task} if zones is None else {"task": task, "education_zones": zones}


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
