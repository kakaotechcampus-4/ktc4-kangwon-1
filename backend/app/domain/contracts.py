"""공개 결과와 저장 기록이 함께 쓰는 판단·근거·검토 계약입니다.

공개 팀 계약인 DecisionRequest/DecisionResult/Evidence/QuestionSnapshot은 schemas.py에,
공통 Schema·Site·시설/질문 어휘는 schema_types.py에, AI 도구 입력과 function 정의는
ai/tool_contracts.py에 둡니다.
"""

from typing import Annotated, Literal, Self, get_args

from pydantic import AfterValidator, Field, JsonValue, model_validator

from app.domain.industries.catalog import INDUSTRIES
from app.domain.schema_types import FacilityCode as FacilityCode
from app.domain.schema_types import QuestionField, Schema, Text

FactId = Annotated[
    str,
    Field(pattern=r"^f_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]


def _industry(value: str) -> str:
    if value not in INDUSTRIES:
        raise ValueError("서비스 51개 업종 카탈로그에 없는 코드입니다.")
    return value


IndustryCode = Annotated[
    str, AfterValidator(_industry), Field(json_schema_extra={"enum": sorted(INDUSTRIES)})
]
Metric = Literal[
    "raw_cell",
    "by_time",
    "time_per_hour_share",
    "covered_trade_areas",
    "period_code",
    "mean_daily_per_trade_area",
    "pattern_fit_index",
    "pattern_scale_percentile",
    "pattern_daily_per_trade_area",
    "weekend_index",
    "day_fit_index",
    "age_share",
    "by_time",
    "resident_age_share",
    "worker_age_share",
    "target_age_index",
    "yoy_change",
    "density_per_km2",
    "competition_index",
    "seoul_median_density",
    "daily_total_median",
    "distance_m",
    "facility_distance_ratio",
    "recent_year_close_rate",
    "oldest_year_close_rate",
    "net_change_rate",
    "turnover_rate",
    "close_rate_ratio",
    "net_change_index",
    "turnover_ratio",
    "close_trend_ratio",
    "store_exposure",
    "avg_store_count",
    "zero_filled_sources",
    "seoul_close_rate",
    "seoul_turnover_rate",
    "seoul_net_change_rate",
    "seoul_close_trend_ratio",
    "store_count",
    "opening_count",
    "closing_count",
    "lq",
    "differentiation",
    "place_name",
    "kakao_category",
    "match_status",
    "regulation_status",
    "zone_contains",
    "floor",
    "exclusive_area",
    "space_condition",
    "existing_facilities",
    "industry_preferences",
    "space_requirements",
    "space_fit",
]
Actor = Literal["decision", "examiner", "founder", "customer", "landlord_advocate", "advisor"]
EvaluatorActor = Literal["examiner", "founder", "customer", "landlord_advocate"]

# 평가자 명단과 인원수의 단일 출처입니다. 평가자를 더하거나 빼면 여기만 고칩니다.
EVALUATOR_ACTORS = get_args(EvaluatorActor)
EVALUATOR_COUNT = len(EVALUATOR_ACTORS)
Source = Literal[
    "floating_population",
    "resident_population",
    "worker_population",
    "commercial_area",
    "business_lifecycle",
    "map",
    "regulation",
    "user",
    "baseline",
    "industry_profile",
]
ItemStatus = Literal["observed", "unknown", "not_applicable"]
ScoreItemId = Literal["D1", "D2", "D3", "D4", "C1", "C4", "S1", "S2", "S3", "S4", "L"]
Grade = Annotated[int, Field(ge=0, le=4)]
Ratio = Annotated[float, Field(ge=0, le=1)]
Badge = Literal["추천", "조건부", "보류", "비추천"]
RegulationStatus = Literal["금지", "조건부", "해당 없음", "unknown"]
ErrorCode = Literal[
    "INVALID_ARGUMENT",
    "SOURCE_UNAVAILABLE",
    "SNAPSHOT_MISMATCH",
    "BUDGET_EXCEEDED",
    "TIMEOUT",
    "DUPLICATE_CALL",
    "VERSION_MISMATCH",
    "UNKNOWN_FACT",
    "UNCITABLE",
    "SQL_DENIED",
    "SQL_TIMEOUT",
    "LINEAGE_UNAVAILABLE",
    "MAP_UNAVAILABLE",
    "REGULATION_UNAVAILABLE",
    "ADVISOR_UNAVAILABLE",
    "QUESTION_NOT_ALLOWED",
    "ALREADY_ANSWERED",
    "REPORT_INVALID",
    "L_EVIDENCE_INVALID",
    "REVIEW_UNRESOLVED",
    "DRAFT_MISMATCH",
    "INVALID_REFERENCE",
    "L_STAGE_REQUIRED",
    "L_STAGE_CLOSED",
    "DUPLICATE_INDUSTRY",
]


class ToolError(Schema):
    code: ErrorCode
    message: Annotated[str, Field(min_length=1, max_length=600)]
    retryable: bool = False


class ToolReply[T](Schema):
    status: Literal["ok", "partial", "error"]
    data: T | None = None
    error: ToolError | None = None
    fact_ids: list[FactId] = Field(default_factory=list)
    warnings: list[Text] = Field(default_factory=list)
    truncated: bool = False
    duplicate: bool = False
    missing_fields: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_payload(self) -> Self:
        if self.status == "error":
            if self.error is None or self.data is not None:
                raise ValueError("오류 응답은 오류 정보만 포함해야 합니다.")
        elif self.data is None or self.error is not None:
            raise ValueError("정상·부분 응답은 자료가 필요합니다.")
        return self


class FactView(Schema):
    fact_id: FactId
    source: Source
    metric: Metric
    value: JsonValue
    unit: Text
    period: Text
    spatial_scope: dict[str, JsonValue]
    industry_code: IndustryCode | None = None
    status: ItemStatus
    citable: bool
    calc_version: Text
    provenance_ref: Text

    @model_validator(mode="after")
    def check_observation(self) -> Self:
        comparison_unknown = (
            self.metric == "space_fit"
            and self.status == "unknown"
            and isinstance(self.value, dict)
            and not self.citable
        )
        if (
            self.status != "observed"
            and not comparison_unknown
            and (self.value is not None or self.citable)
        ):
            raise ValueError("미확인·미적용 사실은 null이고 인용 불가여야 합니다.")
        if self.status == "observed" and self.value is None:
            raise ValueError("관측 사실에는 값이 필요합니다.")
        return self


class CodeItemCalculation(Schema):
    """원래 관측 등급과 분리한 채점 기여입니다. 관측 근거로 인용하지 않습니다."""

    method: Literal["S2_half-v1"]
    weight: Annotated[float, Field(gt=0, le=30)]
    points: Annotated[float, Field(ge=0, le=30)]
    basis: Text
    estimated: bool

    @model_validator(mode="after")
    def check_weight(self) -> Self:
        if self.points > self.weight:
            raise ValueError("보완 기여는 항목 배점을 초과할 수 없습니다.")
        return self


class CodeCalculation(Schema):
    method: Literal["S2_half-v1"]
    code_points: Annotated[float, Field(ge=0, le=90)]
    ranking_points: Annotated[float, Field(ge=0, le=100)]
    applicable_weight: Annotated[float, Field(ge=0, le=90)]
    raw_points: Annotated[float, Field(ge=0, le=90)]
    estimated_points: Annotated[float, Field(ge=0, le=90)]

    @model_validator(mode="after")
    def check_contributions(self) -> Self:
        if not self.estimated_points <= self.raw_points <= self.applicable_weight + 1e-8:
            raise ValueError("보완 추정·합계·적용 배점이 맞지 않습니다.")
        expected = 90 * self.raw_points / self.applicable_weight if self.applicable_weight else 0
        if abs(self.code_points - expected) > 1e-8:
            raise ValueError("코드 점수의 90점 환산이 맞지 않습니다.")
        return self


class MapSearchInput(Schema):
    industry_code: IndustryCode | None = None
    facility_code: FacilityCode | None = None
    radius_m: Annotated[int, Field(ge=50, le=500)]
    limit: Annotated[int, Field(ge=1, le=20)] = 20

    @model_validator(mode="after")
    def check_mode(self) -> Self:
        if (self.industry_code is None) == (self.facility_code is None):
            raise ValueError("업종과 시설 중 하나만 지정해야 합니다.")
        return self


class UserQuestion(Schema):
    field: QuestionField
    question: Annotated[str, Field(min_length=1, max_length=200)]
    reason: Annotated[str, Field(min_length=1, max_length=200)]


class TextSegment(Schema):
    type: Literal["text"]
    text: Text


class FactReferenceSegment(Schema):
    type: Literal["fact"]
    fact_id: FactId
    format: Literal["count", "percent", "rate", "distance", "text"]


FactSegment = Annotated[TextSegment | FactReferenceSegment, Field(discriminator="type")]


class Candidate(Schema):
    industry_code: IndustryCode
    reasons_segments: list[FactSegment] = Field(default_factory=list)
    risks_segments: list[FactSegment] = Field(default_factory=list)
    confirmation_conditions_segments: list[FactSegment] = Field(default_factory=list)
    fact_ids: list[FactId] = Field(default_factory=list, max_length=32)


class LSelection(Schema):
    basis: Literal["all_industries"]
    code_score_snapshot_id: Text
    code_lower_rank: Annotated[int, Field(ge=1, le=51)]
    reason: Text
    reason_fact_ids: list[FactId] = Field(default_factory=list, max_length=12)


class NewFactor(Schema):
    direction: Literal["favorable", "adverse", "neutral"]
    claim: Text
    fact_ids: list[FactId] = Field(min_length=1, max_length=12)
    major_constraint: bool = False
    space_fit_component: (
        Literal["floor", "area", "kitchen", "ventilation", "water_supply"] | None
    ) = None


class LRecord(Schema):
    industry_code: IndustryCode
    selection: LSelection
    review_state: Literal["reviewed", "unreviewed"]
    advisor_unavailable: bool = False
    status: Literal["observed", "unknown"]
    grade: Grade | None
    new_factors: list[NewFactor] = Field(default_factory=list)
    checked_questions: list[Text] = Field(default_factory=list)
    tool_call_ids: list[Text] = Field(default_factory=list)
    advisor_consult_ids: list[Text] = Field(default_factory=list, max_length=2)
    limitations: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_review(self) -> Self:
        if (self.status == "observed") != (self.grade is not None):
            raise ValueError("판단 상태와 등급이 맞지 않습니다.")
        if self.status == "observed" and (
            self.review_state != "reviewed" or not self.tool_call_ids or not self.checked_questions
        ):
            raise ValueError("판단 등급에는 실제 확인 질문·도구 기록이 필요합니다.")
        if self.status == "observed" and self.grade != 2 and not self.new_factors:
            raise ValueError("중립 이외 등급에는 새 근거가 필요합니다.")
        if self.status == "unknown" and not self.limitations:
            raise ValueError("판단 미확인에는 이유가 필요합니다.")
        return self


class ReviewIssue(Schema):
    issue_id: Text
    industry_code: IndustryCode | None = None
    target: Literal["fact", "score", "L", "claim", "condition"]
    kind: Literal[
        "factual_error", "duplicate_score", "missing_evidence", "scope_mismatch", "action_condition"
    ]
    comment: Text
    fact_ids: list[FactId] = Field(default_factory=list, max_length=5)
    suggested_check: Text


class ReviewResolution(Schema):
    issue_id: Text
    disposition: Literal["accepted", "partial", "rejected"]
    reason: Text
    fact_ids: list[FactId] = Field(default_factory=list, max_length=12)
    applied: list[Text] = Field(default_factory=list)
    not_applied: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_reason(self) -> Self:
        if self.disposition == "rejected" and not self.fact_ids:
            raise ValueError("rejected에는 근거 fact_ids를 한 개 이상 넣으세요.")
        if self.disposition == "partial" and (not self.applied or not self.not_applied):
            raise ValueError(
                "partial이면 applied와 not_applied를 각각 채우세요. "
                "나눌 수 없으면 accepted나 rejected로 바꾸세요."
            )
        return self


class ReportProposal(Schema):
    summary_segments: list[FactSegment] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list, max_length=5)
    excluded_candidates: list[Candidate] = Field(default_factory=list, max_length=5)
    limitations_segments: list[FactSegment] = Field(default_factory=list)


class MapPlace(Schema):
    place_id: Text
    name: Text
    kakao_category: Text
    distance_fact_id: FactId
    match_status: Literal["category_match", "name_match", "unknown"]
    match_rule_id: Text | None = None
    fact_ids: list[FactId] = Field(min_length=1)


class MapResult(Schema):
    observation_id: Text
    places: list[MapPlace] = Field(max_length=20)
    coverage: Ratio
    has_more: bool


class IndustryRestriction(Schema):
    industry_code: IndustryCode
    status: RegulationStatus
    scope: Literal["whole", "partial", "none", "unknown"]
    fact_ids: list[FactId] = Field(default_factory=list)


class RegulationResult(Schema):
    status: Literal["ok", "partial", "error"]
    queried_at: Text
    contains_verified: bool
    zones: list[dict[str, JsonValue]]
    fact_ids: list[FactId]
    industry_restrictions: list[IndustryRestriction]
    limitations: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_error(self) -> Self:
        if self.status == "error" and any(
            r.status != "unknown" for r in self.industry_restrictions
        ):
            raise ValueError("규제 조회 오류는 해당 없음이 아니라 unknown입니다.")
        return self


class AdvisorInterpretation(Schema):
    claim: Text
    fact_ids: list[FactId] = Field(min_length=1, max_length=12)
    conditions: list[Text]
    confidence: Literal["high", "medium", "low"]


class AdvisorAnswer(Schema):
    consult_id: Text
    status: Literal["ok", "unavailable"]
    interpretations: list[AdvisorInterpretation] = Field(default_factory=list)
    missing_facts: list[Text] = Field(default_factory=list)
    limitations: list[Text] = Field(default_factory=list)


class ConditionExcludedCandidate(Schema):
    industry_code: IndustryCode
    industry_name: Text
    reasons: list[Text] = Field(min_length=1, max_length=6)
    score_rank: Annotated[int, Field(ge=1, le=51)]


class RankedIndustry(Schema):
    industry_code: IndustryCode
    industry_name: Text
    rank: Annotated[int, Field(ge=1, le=51)]
    ai_excluded: bool = False


class RegulationExcludedIndustry(Schema):
    industry_code: IndustryCode
    industry_name: Text


class ScorecardSummary(Schema):
    industry_code: IndustryCode
    code_points: Annotated[float, Field(ge=0, le=90)]
    L_points: Annotated[float, Field(ge=0, le=10)] | None
    L_status: Literal["observed", "unknown"]
    A: Annotated[float, Field(ge=0, le=100)]
    B: Annotated[float, Field(ge=0, le=100)]
    H: Annotated[float, Field(ge=0, le=100)]
    lower_ratio: Ratio | None
    upper_ratio: Ratio | None
    coverage: Ratio | None
    demand_coverage: Ratio | None
    competition_coverage: Ratio | None
    G: RegulationStatus
    badge: Badge
    confirmation_conditions: list[Text] = Field(default_factory=list)
    calculation: CodeCalculation | None = None

    @model_validator(mode="after")
    def check_intervals(self) -> Self:
        if self.calculation and (
            abs(self.calculation.code_points - self.code_points) > 1e-8
            or abs(self.calculation.ranking_points - self.code_points - (self.L_points or 0)) > 1e-8
        ):
            raise ValueError("코드 점수·L·최종 순위 점수가 맞지 않습니다.")
        if not self.B <= self.H <= self.A:
            raise ValueError("하한 ≤ 상한 ≤ 적용 배점이어야 합니다.")
        if (self.L_status == "observed") != (self.L_points is not None):
            raise ValueError("판단 상태와 판단 점수가 맞지 않습니다.")
        if self.A == 0:
            if any(v is not None for v in (self.lower_ratio, self.upper_ratio, self.coverage)):
                raise ValueError("적용 배점 0이면 비율은 null입니다.")
        elif self.lower_ratio is None or self.upper_ratio is None or self.coverage is None:
            raise ValueError("적용 배점이 있으면 구간 비율·coverage가 필요합니다.")
        elif (
            abs(self.lower_ratio - self.B / self.A) > 1e-8
            or abs(self.upper_ratio - self.H / self.A) > 1e-8
        ):
            raise ValueError("점수 구간 비율이 적용 배점과 맞지 않습니다.")
        if self.G == "금지" and self.badge != "비추천":
            raise ValueError("규제 금지는 비추천이어야 합니다.")
        return self


class FinalCandidate(ScorecardSummary):
    industry_name: Text
    reasons_segments: list[FactSegment]
    risks_segments: list[FactSegment] = Field(default_factory=list)
    confirmation_conditions_segments: list[FactSegment] = Field(default_factory=list)
    fact_ids: list[FactId] = Field(default_factory=list)
    review_state: Literal["reviewed", "unreviewed"]


class CustomerCheck(Schema):
    item: Literal["K1", "K2", "K3", "K4", "K6"]
    status: ItemStatus
    weight: Annotated[int, Field(ge=0, le=100)]
    points: Annotated[float, Field(ge=0, le=100)] | None
    fact_ids: list[FactId] = Field(default_factory=list, max_length=12)
    note: Text

    @model_validator(mode="after")
    def check_points(self) -> Self:
        if (self.status == "observed") != (self.points is not None):
            raise ValueError("관측 항목에만 점수를 채웁니다.")
        if self.points is not None and self.points > self.weight:
            raise ValueError("점수는 배점을 넘을 수 없습니다.")
        return self


class CustomerCandidateScore(Schema):
    industry_code: IndustryCode
    rank: Annotated[int, Field(ge=1, le=5)]
    checks: list[CustomerCheck] = Field(min_length=5, max_length=5)
    points: Annotated[float, Field(ge=0, le=100)]
    applicable_weight: Annotated[int, Field(ge=0, le=100)]
    ratio: Ratio | None


class CustomerRubric(Schema):
    """손님 평가표 v1. K1~K4는 코드, K6만 모델 점수입니다. 판정은 코드 규칙으로 계산합니다."""

    version: Literal["customer-v1"] = "customer-v1"
    candidates: list[CustomerCandidateScore] = Field(default_factory=list, max_length=5)
    ratio: Ratio | None
    verdict_basis: Text
    model_status: Literal["completed", "failed"]


class EvaluatorReview(Schema):
    actor: EvaluatorActor
    status: Literal["completed", "failed"]
    review_id: Text | None = None
    verdict: Literal["agree", "conditional", "oppose"] | None = None
    issues: list[ReviewIssue] = Field(max_length=4)
    error_code: ErrorCode | None = None
    customer_rubric: CustomerRubric | None = None

    @model_validator(mode="after")
    def check_status(self) -> Self:
        if self.status == "completed" and (
            self.review_id is None or self.verdict is None or self.error_code is not None
        ):
            raise ValueError("완료 평가에는 검토 ID·판정이 필요합니다.")
        if self.status == "failed" and (self.verdict is not None or self.issues):
            raise ValueError("실패 평가는 동의나 검토 의견으로 취급하지 않습니다.")
        return self


def error(code, message):
    return ToolReply(status="error", error=ToolError(code=code, message=message))
