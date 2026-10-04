"""주소 처리와 분석 에이전트 실행 흐름을 연결합니다.

주소 → 좌표 → 분석 에이전트 병렬 실행 → 최종판단까지가 한 흐름입니다.
세 분석기는 같은 요청 설정을 명시적으로 전달받습니다.
한 에이전트가 실패해도 나머지는 계속 돕니다.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from functools import partial

from pydantic import ValidationError

from app.agents import business_lifecycle, commercial_area, floating_population
from app.agents.business_lifecycle import supplement as lifecycle_supplement
from app.agents.commercial_area import supplement as commercial_supplement
from app.agents.data_models import parse_data
from app.schemas import (
    DEFAULT_RADIUS_M,
    AgentAnalysis,
    AgentError,
    AgentId,
    AnalysisTask,
    Site,
    SupplementOperation,
    validate_radius,
)
from app.services.settings import ExecutionSettings, validate_timeout

from . import tools

AnalysisAgent = Callable[[AnalysisTask], Awaitable[AgentAnalysis]]
AgentRegistry = dict[AgentId, AnalysisAgent]

__all__ = [
    "AgentRegistry",
    "AnalysisAgent",
    "build_react_agents",
    "build_supplement_tools",
    "prepare_task",
    "run_agents",
]


async def prepare_task(
    address: str,
    *,
    resolve: Callable[[str], Awaitable[Site]],
    radius_m: int = DEFAULT_RADIUS_M,
    request_id: str | None = None,
) -> AnalysisTask:
    """주소 변환 도구를 호출하고 공통 입력을 검증합니다."""
    radius_m = validate_radius(radius_m)
    cleaned = address.strip()
    if not cleaned:
        raise ValueError("주소가 비어 있습니다.")
    resolved = Site.model_validate(await resolve(cleaned))
    return AnalysisTask(
        request_id=uuid.uuid4().hex if request_id is None else request_id,
        site=resolved,
        radius_m=radius_m,
    )


def build_react_agents(settings: ExecutionSettings | None = None) -> AgentRegistry:
    """등록 시 외부 호출 없이 세 실제 분석기를 같은 설정 묶음에 연결합니다."""
    settings = settings or ExecutionSettings.from_env()

    async def guarded(
        task: AnalysisTask, *, agent_id: AgentId, analyze: AnalysisAgent
    ) -> AgentAnalysis:
        if (task.site.latitude, task.site.longitude) == (0, 0):
            return AgentAnalysis(
                request_id=task.request_id,
                agent_id=agent_id,
                status="error",
                error=AgentError(
                    code="INVALID_ANALYSIS_COORDINATES",
                    message="목업 좌표 (0, 0)는 실제 분석에 사용할 수 없습니다.",
                ),
            )
        return await analyze(task)

    return {
        "floating_population": partial(
            guarded,
            agent_id="floating_population",
            analyze=partial(
                floating_population.analyze,
                settings=settings.floating,
            ),
        ),
        "business_lifecycle": partial(
            guarded,
            agent_id="business_lifecycle",
            analyze=partial(
                business_lifecycle.analyze,
                settings=settings.lifecycle,
            ),
        ),
        "commercial_area": partial(
            guarded,
            agent_id="commercial_area",
            analyze=partial(commercial_area.analyze, settings=settings.commercial),
        ),
    }


def build_supplement_tools(settings: ExecutionSettings) -> list[tools.SupplementTool]:
    """등록만으로 외부 호출하지 않으며 유동인구 보완은 연결하지 않습니다."""
    return [
        tools.SupplementTool(
            operation=SupplementOperation(
                agent_id="commercial_area",
                operation="retry_lq_baseline",
                description=(
                    "최초 주변 비교 조회 실패 시 경쟁 판단에 꼭 필요한 자료만 재조회합니다. "
                    "주 반경 점포는 재조회하지 않습니다."
                ),
            ),
            execute=partial(commercial_supplement.supplement, settings=settings.commercial),
            eligible=partial(commercial_supplement.eligible, settings=settings.commercial),
            accept=commercial_supplement.accept,
        ),
        tools.SupplementTool(
            operation=SupplementOperation(
                agent_id="business_lifecycle",
                operation="fetch_quarter_details",
                description=(
                    "추세 판단에 필요할 때 동일 상권·기간의 분기별 건수·폐업률을 확인합니다. "
                    "최대 12개 분기이며 없는 분기를 채우거나 점수를 재계산하지 않습니다."
                ),
            ),
            execute=partial(lifecycle_supplement.supplement, settings=settings.lifecycle),
            eligible=lifecycle_supplement.eligible,
            accept=lifecycle_supplement.accept,
        ),
    ]


def _crash_to_analysis(task: AnalysisTask, agent_id: AgentId, _exc: BaseException) -> AgentAnalysis:
    return AgentAnalysis(
        request_id=task.request_id,
        agent_id=agent_id,
        status="error",
        error=AgentError(
            code="AGENT_CRASHED",
            message="분석 에이전트 실행에 실패했습니다.",
        ),
    )


async def run_agents(
    task: AnalysisTask,
    agents: AgentRegistry,
    *,
    on_analysis_completed: Callable[[AgentAnalysis], Awaitable[None]] | None = None,
    agent_timeout: float = 180.0,
) -> list[AgentAnalysis]:
    """등록된 분석 에이전트를 동시에 실행합니다."""
    if not agents:
        raise ValueError("실행할 분석 에이전트가 없습니다.")
    validate_timeout(agent_timeout)

    async def run_one(agent_id: AgentId) -> AgentAnalysis:
        try:
            async with asyncio.timeout(agent_timeout) as deadline:
                result = await agents[agent_id](task)
        except ValidationError:
            raise
        except Exception as exc:
            result = _crash_to_analysis(task, agent_id, exc)
            if isinstance(exc, TimeoutError) and deadline.expired():
                result.error = AgentError(
                    code="AGENT_TIMEOUT", message="분석 제한시간이 초과됐습니다."
                )
        # 계약 오류와 저장 실패는 분석 함수의 실행 오류로 바꾸지 않습니다.
        analysis = AgentAnalysis.model_validate(result)
        if analysis.agent_id != agent_id or analysis.request_id != task.request_id:
            raise ValueError("분석 결과의 요청 ID 또는 에이전트 ID가 일치하지 않습니다.")
        if analysis.data:
            parse_data(analysis.agent_id, analysis.data)
        if on_analysis_completed is not None:
            await on_analysis_completed(analysis)
        return analysis

    results = await asyncio.gather(*(run_one(key) for key in agents), return_exceptions=True)
    analyses = []
    for result in results:
        if isinstance(result, BaseException):
            raise result
        analyses.append(result)
    return analyses
