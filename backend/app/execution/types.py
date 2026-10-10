"""저장 구현과 무관한 실행 상태 타입입니다."""

from typing import Any, TypedDict


class ExecutionCapabilities(TypedDict, total=False):
    evaluators: bool
    map: bool
    supplements: list[list[str]]


class ExecutionState(TypedDict, total=False):
    capabilities: ExecutionCapabilities
    budget: dict[str, Any]
    elapsed_seconds: float
    time_limit: float
    evaluation_skipped: str
    evaluation_start_round: int
