"""오케스트레이터가 사용하는 기존 주소 변환 도구를 공개합니다.

목업 실행에서는 이 도구 대신 별도의 주소 변환 대역을 주입합니다.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.address import resolve_site
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


__all__ = ["resolve_site", "SupplementTool"]
