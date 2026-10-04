"""오케스트레이션 그래프가 쓰는 보완 도구와 지도 조회 타입을 정의합니다."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.schemas import (
    AgentAnalysis,
    AnalysisTask,
    MapLookupPlan,
    MapObservation,
    SupplementOperation,
)

MapLookup = Callable[[AnalysisTask, MapLookupPlan], Awaitable[MapObservation]]
OnMapRequested = Callable[[AnalysisTask, MapLookupPlan], Awaitable[None]]
OnMapCompleted = Callable[[MapObservation], Awaitable[None]]


@dataclass(frozen=True)
class SupplementTool:
    """실행 가능 조건과 부분 작업 함수를 함께 등록합니다."""

    operation: SupplementOperation
    execute: Callable[[AnalysisTask, AgentAnalysis], Awaitable[AgentAnalysis]]
    eligible: Callable[[AnalysisTask, AgentAnalysis], bool]
    accept: Callable[[AgentAnalysis, AgentAnalysis], bool] | None = None
