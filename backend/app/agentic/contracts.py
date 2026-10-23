"""새 구조의 검증 계약과 OpenAI 호환 function 정의입니다.

도구 입출력·채점·검토 계약을 정의합니다. 공개 팀 계약인
DecisionRequest/DecisionResult/Evidence/QuestionSnapshot은 app.schemas에 둡니다.
공통 Schema·Site·시설/질문 어휘는 app.schema_types에서 재사용합니다.
"""

from copy import deepcopy
from typing import Annotated, Any, Literal, Self, get_args

from pydantic import AfterValidator, Field, JsonValue, model_validator

from app.industries.catalog import INDUSTRIES
from app.schema_types import FacilityCode as FacilityCode
from app.schema_types import QuestionField, Schema, Text

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
ToolName = Literal[
    "get_scorecard",
    "get_facts",
    "query_raw",
    "map_search",
    "check_regulation",
    "ask_advisor",
    "ask_user",
    "submit_l",
    "submit_draft",
    "submit_review",
]
Actor = Literal["decision", "examiner", "founder", "customer", "landlord_advocate", "advisor"]
EvaluatorActor = Literal["examiner", "founder", "customer", "landlord_advocate"]
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
    message: Annotated[str, Field(min_length=1, max_length=300)]
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


class ScoreItem(Schema):
    item: ScoreItemId
    status: ItemStatus
    grade: Grade | None
    points: Annotated[float, Field(ge=0, le=15)] | None
    fact_ids: list[FactId] = Field(max_length=32)

    @model_validator(mode="after")
    def check_observation(self) -> Self:
        if self.status == "observed":
            if self.grade is None or self.points is None or not self.fact_ids:
                raise ValueError("관측 문항에는 등급·점수·근거가 필요합니다.")
        elif self.grade is not None or self.points is not None:
            raise ValueError("미확인·미적용 문항에는 등급·점수를 채우지 않습니다.")
        return self


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

    @model_validator(mode="after")
    def check_intervals(self) -> Self:
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


class Scorecard(ScorecardSummary):
    items: list[ScoreItem] = Field(min_length=11, max_length=11)

    @model_validator(mode="after")
    def check_items(self) -> Self:
        if {item.item for item in self.items} != set(get_args(ScoreItemId)):
            raise ValueError("11개 문항을 중복 없이 포함해야 합니다.")
        return self


class GetScorecardInput(Schema):
    industry_codes: list[IndustryCode] | None = Field(default=None, min_length=1, max_length=51)
    mode: Literal["summary", "detail"] = "summary"
    limit: Annotated[int, Field(ge=1, le=32)] = 32
    cursor: Text | None = None

    @model_validator(mode="after")
    def check_detail_limit(self) -> Self:
        if self.mode == "detail" and self.limit > 5:
            raise ValueError("상세 조회는 한 번에 최대 5개입니다.")
        return self


class GetFactsInput(Schema):
    fact_ids: list[FactId] | None = Field(default=None, min_length=1, max_length=32)
    industry_code: IndustryCode | None = None
    source: Source | None = None
    metrics: list[Metric] | None = Field(default=None, min_length=1, max_length=8)
    limit: Annotated[int, Field(ge=1, le=51)] = 32
    cursor: Text | None = None

    @model_validator(mode="after")
    def check_mode(self) -> Self:
        filters = (self.industry_code, self.source, self.metrics)
        if self.fact_ids is not None:
            if any(v is not None for v in filters) or self.cursor is not None:
                raise ValueError("fact_ids와 검색 조건을 함께 넣을 수 없습니다.")
        elif self.source == "industry_profile" and self.metrics == ["space_fit"]:
            pass
        elif any(v is None for v in filters):
            raise ValueError("업종·출처·지표를 모두 지정해야 합니다.")
        elif self.limit > 32:
            raise ValueError("일반 사실 조회는 최대 32개입니다.")
        return self


class QueryRawInput(Schema):
    sql: Annotated[str, Field(min_length=1, max_length=4000)]
    params: dict[str, JsonValue] | list[JsonValue] = Field(default_factory=dict)
    max_rows: Annotated[int, Field(ge=1, le=50)] = 50


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


class CheckRegulationInput(Schema):
    pass


class AskAdvisorInput(Schema):
    question: Annotated[str, Field(min_length=1, max_length=800)]
    fact_ids: list[FactId] = Field(min_length=1, max_length=12)
    industry_codes: list[IndustryCode] | None = Field(default=None, min_length=1, max_length=3)


class UserQuestion(Schema):
    field: QuestionField
    question: Annotated[str, Field(min_length=1, max_length=200)]
    reason: Annotated[str, Field(min_length=1, max_length=200)]


class AskUserInput(Schema):
    questions: list[UserQuestion] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        if len({q.field for q in self.questions}) != len(self.questions):
            raise ValueError("질문 항목이 중복됩니다.")
        return self


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
            raise ValueError("기각에는 근거 fact_id가 필요합니다.")
        if self.disposition == "partial" and (not self.applied or not self.not_applied):
            raise ValueError("일부 반영은 반영·미반영 부분을 나눠야 합니다.")
        return self


class ReportProposal(Schema):
    summary_segments: list[FactSegment] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list, max_length=5)
    excluded_candidates: list[Candidate] = Field(default_factory=list, max_length=5)
    limitations_segments: list[FactSegment] = Field(default_factory=list)


class LFactorInput(Schema):
    fact_id: Annotated[str, Field(min_length=1, max_length=40)]
    direction: Literal["favorable", "adverse"]
    severe: bool = False


class LInput(Schema):
    industry_code: IndustryCode
    factors: list[LFactorInput] = Field(default_factory=list)
    neutral: bool = False
    fact_ids: list[str] = Field(default_factory=list)
    note: Annotated[str, Field(max_length=80)] = ""

    @model_validator(mode="after")
    def check_neutral(self) -> Self:
        if self.neutral and (self.factors or not self.fact_ids):
            raise ValueError("중립은 factors 없이 확인한 fact_ids가 필요합니다.")
        return self


class SubmitLInput(Schema):
    # 한 행의 오류가 다른 업종을 막지 않도록 handler에서 행별로 검증합니다.
    L_records: list[dict[str, Any]] = Field(default_factory=list)
    finish: bool = False

    @model_validator(mode="after")
    def check_batch(self) -> Self:
        if not self.L_records and not self.finish:
            raise ValueError("빈 묶음은 종료를 명시해야 합니다.")
        return self


class SubmitDraftInput(Schema):
    phase: Literal["draft", "final"]
    report: ReportProposal
    review_resolutions: list[ReviewResolution] = Field(default_factory=list, max_length=16)


class FitCheck(Schema):
    """손님 평가자 전용. 손님 입장에서 추천과 근거가 맞는지 K6 배점의 다섯 값 중 하나로 매깁니다."""

    industry_code: IndustryCode
    points: Annotated[float, Field(ge=0, le=40, multiple_of=10)] | None
    fact_ids: list[FactId] = Field(default_factory=list, max_length=5)
    reason: Text


class SubmitReviewInput(Schema):
    draft_id: Text
    verdict: Literal["agree", "conditional", "oppose"]
    issues: list[ReviewIssue] = Field(max_length=4)
    fit_checks: list[FitCheck] = Field(default_factory=list, max_length=5)


class ScorecardResult(Schema):
    scorecards: list[Scorecard] = Field(default_factory=list, max_length=5)
    summaries: list[ScorecardSummary] = Field(default_factory=list, max_length=32)
    next_cursor: Text | None = None


class FactsResult(Schema):
    facts: list[FactView] = Field(max_length=51)
    provenance_refs: list[Text] = Field(default_factory=list)
    next_cursor: Text | None = None


class SubmitLResult(Schema):
    submitted_count: Annotated[int, Field(ge=0, le=51)]
    remaining_count: Annotated[int, Field(ge=0, le=51)]
    closed: bool
    score_snapshot_id: Text | None = None
    scorecard: ScorecardResult | None = None
    accepted: list[IndustryCode] = Field(default_factory=list)
    ignored: list[IndustryCode] = Field(default_factory=list)
    rejected: list[dict[str, str]] = Field(default_factory=list)
    unsubmitted: list[IndustryCode] = Field(default_factory=list)


class RawQueryRow(Schema):
    raw_row_refs: list[Text]
    values: dict[str, JsonValue]
    fact_ids: list[FactId] = Field(default_factory=list)


class RawQueryResult(Schema):
    columns: list[Text]
    rows: list[RawQueryRow] = Field(max_length=50)
    uncitable_columns: list[Text] = Field(default_factory=list)


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


class QuestionSessionRef(Schema):
    question_session_id: Text
    status: Literal["waiting_for_input"] = "waiting_for_input"


class SubmitResult(Schema):
    report_id: Text
    validation_status: Literal["valid"]
    rendered_preview_ref: Text
    score_snapshot_id: Text


class ReviewRef(Schema):
    review_id: Text
    status: Literal["submitted"] = "submitted"


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


TOOL_INPUTS: dict[str, type[Schema]] = {
    "get_scorecard": GetScorecardInput,
    "get_facts": GetFactsInput,
    "query_raw": QueryRawInput,
    "map_search": MapSearchInput,
    "check_regulation": CheckRegulationInput,
    "ask_advisor": AskAdvisorInput,
    "ask_user": AskUserInput,
    "submit_l": SubmitLInput,
    "submit_draft": SubmitDraftInput,
    "submit_review": SubmitReviewInput,
}
_TOOL_DESCRIPTIONS = {
    "get_scorecard": "코드 점수·근거를 조회합니다. 전체 업종 동일 검토, 상세는 최대 다섯 개입니다.",
    "get_facts": (
        "fact_ids 또는 업종·source·metrics로 조회. industry_profile/space_fit은 전체 묶음 조회."
    ),
    "query_raw": "승인 뷰 SELECT로 원문을 최대 50행 확인합니다. 쓰기·집계 인용은 금지합니다.",
    "map_search": (
        "기존 fact로 설명되지 않는 경쟁·시설 조건이 있을 때 업종 또는 시설 하나만 검색합니다."
    ),
    "check_regulation": "현재 좌표의 교육환경보호구역과 업종 제한을 확인합니다.",
    "ask_advisor": "코드와 새 근거가 충돌할 때 질문과 fact_id만 보내 자문합니다.",
    "ask_user": (
        "미확인 핵심 상가 조건을 처음에 한 번 묶어 최대 3개 질문합니다. "
        "이미 답한 항목은 제외합니다."
    ),
    "submit_l": "업종·근거 별칭·유리/불리만 제출. 상태·등급은 코드 계산. 행별 채택, 중복 무시.",
    "submit_draft": (
        "L 종료 뒤 재계산 Top5로 보고서 제출. 후보/제외 각각 최대 다섯 개, L 입력 금지."
    ),
    "submit_review": (
        "읽기 최대 3회 뒤 한 번 제출합니다. 실제 fact_id로 최대 4개 지적과 확인 조건을 남깁니다."
    ),
}


def _function_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """참조를 펼치고 비엄격 function 형식에 불필요한 메타정보를 제거합니다.

    런타임 모델의 Field·교차 검증은 유지합니다. Pydantic discriminator의 oneOf는
    anyOf로 내보내며, 엄격 출력의 모든 필드 required 제약은 적용하지 않습니다.
    """
    definitions = schema.get("$defs", {})

    def visit(node: Any) -> Any:
        if isinstance(node, list):
            return [visit(v) for v in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            ref = node["$ref"]
            if not ref.startswith("#/$defs/"):
                raise ValueError("외부 JSON Schema 참조는 허용하지 않습니다.")
            return visit(
                definitions[ref.removeprefix("#/$defs/")]
                | {k: v for k, v in node.items() if k != "$ref"}
            )
        return {
            "anyOf" if k == "oneOf" else k: visit(v)
            for k, v in node.items()
            if k not in {"$defs", "title", "default", "discriminator"}
        }

    return visit(deepcopy(schema))


def tool_definitions() -> list[dict[str, Any]]:
    """Chat Completions에 전달할 10개 function 정의입니다. 실행기가 역할 권한을 거릅니다."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": _TOOL_DESCRIPTIONS[name],
                "strict": False,
                "parameters": _tool_schema(name, model),
            },
        }
        for name, model in TOOL_INPUTS.items()
    ]


def _tool_schema(name, model):
    schema = model.model_json_schema()
    if name == "submit_l":
        row = LInput.model_json_schema()
        schema.setdefault("$defs", {}).update(row.pop("$defs", {}))
        schema["properties"]["L_records"]["items"] = row
    schema = _function_schema(schema)

    def references(node):
        if isinstance(node, dict):
            pattern = node.get("pattern", "")
            if pattern.startswith("^f_"):
                node["pattern"] = "^(?:[0-9a-f]{8}|" + pattern[1:-1] + ")$"
            for child in node.values():
                references(child)
        elif isinstance(node, list):
            for child in node:
                references(child)

    references(schema)
    return schema
