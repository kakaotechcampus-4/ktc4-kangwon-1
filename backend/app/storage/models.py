"""저장소와 서비스가 공유하는 재개 자료의 내부 타입입니다."""

from dataclasses import dataclass
from typing import Any, TypedDict

from app.execution.types import ExecutionCapabilities as ExecutionCapabilities
from app.execution.types import ExecutionState as ExecutionState
from app.schemas import (
    AgentBrief,
    AnalysisMode,
    AnalysisTask,
    DecisionRequest,
    Evaluation,
    EvaluationLogEntry,
    LandlordAnswer,
    MapQuery,
    Site,
    SpecialistAnswer,
    SupplementEvent,
    WaitingForInput,
)


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


class DecisionFailure(TypedDict):
    failed_at: str
    error: dict[str, Any]
    diagnostics: list[dict[str, Any]]


class AnalysisEvent(TypedDict):
    seq: int
    at: str
    stage: str
    event: str
    detail: dict[str, Any]


class MapLookupState(TypedDict):
    status: str
    observation: dict[str, Any] | None


@dataclass(frozen=True)
class StoredRequest:
    request_id: str
    input_address: str
    catalog_version: str | None
    analysis_mode: AnalysisMode
    radius_m: int | None
    status: str
    created_at: str
    completed_at: str | None


@dataclass(frozen=True)
class StoredAnalysisAttempt:
    attempt: int
    analysis: dict[str, Any]


@dataclass(frozen=True)
class StoredEvaluation:
    draft: dict[str, Any]
    evaluations: list[Evaluation]
    log: list[EvaluationLogEntry]


@dataclass(frozen=True)
class StoredAnalysisDetail:
    request: StoredRequest
    execution: ExecutionState
    site: Any
    result: Any
    error: Any
    analyses: list[StoredAnalysisAttempt]
    supplements: list[dict[str, Any]]
    questions: WaitingForInput | None
    map_status: str | None
    map_observation: dict[str, Any] | None
    evaluation: StoredEvaluation | None
    deliberation: DeliberationState | None
    decision_failures: list[DecisionFailure]
