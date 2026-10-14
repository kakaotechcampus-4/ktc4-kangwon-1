"""공개 팀 계약. 공통 분석 타입은 동일한 클래스로 재사용합니다."""

from typing import Literal, Self, get_args

from pydantic import Field, model_validator

from app.agents.agentic.contracts import (
    EvaluatorActor,
    EvaluatorReview,
    FactId,
    FactSegment,
    FactView,
    FinalCandidate,
    LRecord,
    Ratio,
    RemainingBudget,
    ReviewResolution,
    UserQuestion,
)
from app.legacy_schemas import (
    AGENT_IDS as AGENT_IDS,
)
from app.legacy_schemas import (
    DEFAULT_RADIUS_M as DEFAULT_RADIUS_M,
)
from app.legacy_schemas import (
    EVALUATOR_IDS as EVALUATOR_IDS,
)
from app.legacy_schemas import (
    QUESTION_FIELDS as QUESTION_FIELDS,
)
from app.legacy_schemas import (
    AgentAnalysis as AgentAnalysis,
)
from app.legacy_schemas import (
    AgentBrief as AgentBrief,
)
from app.legacy_schemas import (
    AgentError as AgentError,
)
from app.legacy_schemas import (
    AgentId as AgentId,
)
from app.legacy_schemas import (
    AnalysisMode as AnalysisMode,
)
from app.legacy_schemas import (
    AnalysisTask as AnalysisTask,
)
from app.legacy_schemas import (
    AnswerSubmission as AnswerSubmission,
)
from app.legacy_schemas import (
    Category as Category,
)
from app.legacy_schemas import (
    ConsultPlan as ConsultPlan,
)
from app.legacy_schemas import (
    DecisionContent as DecisionContent,
)
from app.legacy_schemas import (
    Evaluation as Evaluation,
)
from app.legacy_schemas import (
    EvaluationComment as EvaluationComment,
)
from app.legacy_schemas import (
    EvaluationLogEntry as EvaluationLogEntry,
)
from app.legacy_schemas import (
    EvaluationRequest as EvaluationRequest,
)
from app.legacy_schemas import (
    EvaluatorId as EvaluatorId,
)
from app.legacy_schemas import (
    EvidenceRef as EvidenceRef,
)
from app.legacy_schemas import (
    FacilityCode as FacilityCode,
)
from app.legacy_schemas import (
    Finding as Finding,
)
from app.legacy_schemas import (
    IndustryAssessment as IndustryAssessment,
)
from app.legacy_schemas import (
    IndustryCode as IndustryCode,
)
from app.legacy_schemas import (
    IndustryRow as IndustryRow,
)
from app.legacy_schemas import (
    LandlordAnswer as LandlordAnswer,
)
from app.legacy_schemas import (
    LandlordQuestion as LandlordQuestion,
)
from app.legacy_schemas import (
    Latitude as Latitude,
)
from app.legacy_schemas import (
    Longitude as Longitude,
)
from app.legacy_schemas import (
    MapData as MapData,
)
from app.legacy_schemas import (
    MapIndustry as MapIndustry,
)
from app.legacy_schemas import (
    MapLookupPlan as MapLookupPlan,
)
from app.legacy_schemas import (
    MapObservation as MapObservation,
)
from app.legacy_schemas import (
    MapPlace as MapPlace,
)
from app.legacy_schemas import (
    MapQuery as MapQuery,
)
from app.legacy_schemas import (
    MapQueryResult as MapQueryResult,
)
from app.legacy_schemas import (
    MatchStatus as MatchStatus,
)
from app.legacy_schemas import (
    QuestionField as QuestionField,
)
from app.legacy_schemas import (
    QuestionPlan as QuestionPlan,
)
from app.legacy_schemas import (
    QuestionSnapshotV2 as QuestionSnapshotV2,
)
from app.legacy_schemas import (
    RadiusMeters as RadiusMeters,
)
from app.legacy_schemas import Schema, Site, Text
from app.legacy_schemas import (
    Scope as Scope,
)
from app.legacy_schemas import (
    SpecialistAnswer as SpecialistAnswer,
)
from app.legacy_schemas import (
    SpecialistId as SpecialistId,
)
from app.legacy_schemas import (
    SpecialistQuery as SpecialistQuery,
)
from app.legacy_schemas import (
    SupplementEvent as SupplementEvent,
)
from app.legacy_schemas import (
    SupplementOperation as SupplementOperation,
)
from app.legacy_schemas import (
    SupplementPlan as SupplementPlan,
)
from app.legacy_schemas import (
    SupplementRequest as SupplementRequest,
)
from app.legacy_schemas import (
    ToolCallRecord as ToolCallRecord,
)
from app.legacy_schemas import (
    WaitingForInput as WaitingForInput,
)
from app.legacy_schemas import (
    normalize_answers as normalize_answers,
)
from app.legacy_schemas import (
    validate_radius as validate_radius,
)


class Evidence(Schema):
    fact_id: FactId


class DecisionRequest(Schema):
    request_id: Text
    run_id: Text
    site: Site
    snapshot_id: Text
    rubric_version: Literal["v0.8"] = "v0.8"
    tool_contract_version: Literal["1"] = "1"
    remaining_budget: RemainingBudget


class DecisionResult(Schema):
    schema_version: Literal["2.0"] = "2.0"
    rubric_version: Literal["v0.8"] = "v0.8"
    tool_contract_version: Literal["1"] = "1"
    request_id: Text
    run_id: Text
    report_id: Text
    snapshot_id: Text
    score_snapshot_id: Text
    summary_segments: list[FactSegment]
    top5: list[FinalCandidate] = Field(max_length=5)
    excluded_candidates: list[FinalCandidate] = Field(default_factory=list, max_length=5)
    facts: list[FactView]
    L_records: list[LRecord] = Field(max_length=51)
    evaluator_reviews: list[EvaluatorReview] = Field(min_length=4, max_length=4)
    review_completeness: Ratio
    review_resolutions: list[ReviewResolution] = Field(default_factory=list, max_length=16)
    confirmation_conditions_segments: list[FactSegment]
    limitations_segments: list[FactSegment]

    @model_validator(mode="after")
    def check_reviewers(self) -> Self:
        if {r.actor for r in self.evaluator_reviews} != set(get_args(EvaluatorActor)):
            raise ValueError("평가자 네 명이 중복 없이 필요합니다.")
        if (
            self.review_completeness
            != sum(r.status == "completed" for r in self.evaluator_reviews) / 4
        ):
            raise ValueError("평가 완료 비율이 상태와 맞지 않습니다.")
        codes = [r.industry_code for r in self.top5]
        if len(codes) != len(set(codes)) or any(r.G == "금지" for r in self.top5):
            raise ValueError("Top 5는 업종 중복·규제 금지를 포함할 수 없습니다.")
        return self


class QuestionSnapshot(Schema):
    request: DecisionRequest
    score_snapshot_id: Text
    draft_id: Text | None = None
    adopted_fact_ids: list[FactId] = Field(max_length=64)
    tool_call_hashes: list[Text] = Field(max_length=40)
    question_session_id: Text
    questions: list[UserQuestion] = Field(min_length=1, max_length=3)
