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
from app.schema_types import *  # noqa: F403
from app.schema_types import Schema, Site, Text


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
