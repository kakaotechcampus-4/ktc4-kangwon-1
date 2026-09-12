"""주소 처리와 분석 에이전트 실행 흐름을 연결합니다.

주소 → 좌표 → 분석 에이전트 병렬 실행 → 중재까지가 한 흐름입니다.
아직 구현되지 않은 에이전트는 등록하지 않으며, 중재 에이전트가 그 사실을
`limitations`에 남깁니다. 한 에이전트가 실패해도 나머지는 계속 돕니다.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from functools import partial

from app.address import resolve_site
from app.agents import commercial_area, decision
from app.agents.commercial_area.config import Settings, load_dotenv_if_present
from app.agents.decision.agent import GenerateDecision
from app.schemas import (
    AgentAnalysis,
    AgentError,
    AgentId,
    AnalysisTask,
    DecisionRequest,
    DecisionResult,
    Site,
)

AnalysisAgent = Callable[[AnalysisTask], Awaitable[AgentAnalysis]]
AgentRegistry = dict[AgentId, AnalysisAgent]

__all__ = ["AgentRegistry", "AnalysisAgent", "default_agents", "run_agents", "run_analysis"]


def default_agents(settings: Settings | None = None) -> AgentRegistry:
    """지금 구현된 분석 에이전트만 등록합니다.

    유동인구·개폐업 에이전트가 준비되면 여기에 한 줄씩 추가합니다.
    """
    return {
        commercial_area.AGENT_ID: partial(commercial_area.analyze, settings=settings),
    }


def _crash_to_analysis(task: AnalysisTask, agent_id: AgentId, exc: BaseException) -> AgentAnalysis:
    return AgentAnalysis(
        request_id=task.request_id,
        agent_id=agent_id,
        status="error",
        error=AgentError(
            code="AGENT_CRASHED",
            message=f"{type(exc).__name__}: {exc}"[:500],
        ),
    )


async def run_agents(
    task: AnalysisTask,
    agents: AgentRegistry,
) -> list[AgentAnalysis]:
    """등록된 분석 에이전트를 동시에 실행합니다."""
    if not agents:
        raise ValueError("실행할 분석 에이전트가 없습니다.")

    agent_ids = list(agents)
    results = await asyncio.gather(
        *(agents[agent_id](task) for agent_id in agent_ids),
        return_exceptions=True,
    )
    analyses: list[AgentAnalysis] = []
    for agent_id, result in zip(agent_ids, results, strict=True):
        if isinstance(result, BaseException):
            analyses.append(_crash_to_analysis(task, agent_id, result))
        else:
            analyses.append(result)
    return analyses


async def run_analysis(
    address: str,
    *,
    site: Site | None = None,
    settings: Settings | None = None,
    agents: AgentRegistry | None = None,
    generate: GenerateDecision | None = None,
    request_id: str | None = None,
) -> DecisionResult:
    """주소 하나로 최종 중재 결과까지 만듭니다.

    `site`를 주면 좌표 변환을 건너뜁니다. `agents`와 `generate`는 시험용
    대역을 넣기 위한 자리입니다.
    """
    load_dotenv_if_present()
    settings = settings or Settings.from_env()
    resolved = site or await resolve_site(address, settings)
    task = AnalysisTask(
        request_id=request_id or uuid.uuid4().hex,
        site=resolved,
    )
    analyses = await run_agents(task, agents or default_agents(settings))
    request = DecisionRequest(
        request_id=task.request_id,
        address=resolved.input_address,
        analyses=analyses,
    )
    return await decision.analyze(request, generate=generate)
