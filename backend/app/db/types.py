"""저장소와 서비스가 공유하는 재개 자료의 내부 타입입니다."""

from typing import Any, TypedDict

from app.schemas import (
    AgentBrief,
    AnalysisMode,
    AnalysisTask,
    DecisionRequest,
    LandlordAnswer,
    MapQuery,
    Site,
    SpecialistAnswer,
    SupplementEvent,
)


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


class DeliberationState(TypedDict):
    briefs: list[AgentBrief]
    specialist_answers: list[SpecialistAnswer]
    map_queries: list[MapQuery]
    consult_round: int
    map_attempt: int | None
    execution: ExecutionState


class ResumeBundle(DeliberationState):
    request: DecisionRequest
    site: Site
    answers: list[LandlordAnswer]
    feedback: list[str]
    supplement_context: list[SupplementEvent]
    source_attempts: dict[str, int]
    task: AnalysisTask
    analysis_mode: AnalysisMode
