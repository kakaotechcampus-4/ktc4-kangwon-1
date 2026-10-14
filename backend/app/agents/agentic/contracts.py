"""새 구조의 검증 계약과 OpenAI 호환 function 정의입니다.

PR1~PR6에는 최종 이름의 모델을 모두 이 모듈에 둡니다. PR7에서 팀 계약
DecisionRequest/DecisionResult/Evidence/QuestionSnapshot을 app.schemas로 옮겨
기존 모델을 교체합니다. 공통 Schema·Site·시설/질문 어휘만 재사용하며 실행은 연결하지 않습니다.
"""

from copy import deepcopy
from typing import Annotated, Any, Literal, Self, get_args

from pydantic import AfterValidator, Field, JsonValue, model_validator

from app.industries.catalog import INDUSTRIES
from app.legacy_schemas import FacilityCode as FacilityCode
from app.legacy_schemas import QuestionField, Schema, Text

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
]
ToolName = Literal[
    "get_scorecard",
    "get_facts",
    "query_raw",
    "map_search",
    "check_regulation",
    "ask_advisor",
    "ask_user",
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
]


class ToolError(Schema):
    code: ErrorCode
    message: Annotated[str, Field(min_length=1, max_length=300)]
    retryable: bool = False
    failed_fields: list[Text] = Field(default_factory=list)


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
        if self.status != "observed" and (self.value is not None or self.citable):
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
    limit: Annotated[int, Field(ge=1, le=32)] = 32
    cursor: Text | None = None

    @model_validator(mode="after")
    def check_mode(self) -> Self:
        filters = (self.industry_code, self.source, self.metrics)
        if self.fact_ids is not None:
            if any(v is not None for v in filters) or self.cursor is not None:
                raise ValueError("fact_ids와 검색 조건을 함께 넣을 수 없습니다.")
        elif any(v is None for v in filters):
            raise ValueError("업종·출처·지표를 모두 지정해야 합니다.")
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
    basis: Literal["code_lower_top10", "decision_extra", "outside_scope"]
    code_score_snapshot_id: Text
    code_lower_rank: Annotated[int, Field(ge=1, le=51)]
    reason: Text
    reason_fact_ids: list[FactId] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def check_extra(self) -> Self:
        if self.basis == "decision_extra" and not self.reason_fact_ids:
            raise ValueError("추가 검토 선정에는 근거가 필요합니다.")
        if self.basis == "code_lower_top10" and self.code_lower_rank > 10:
            raise ValueError("상위 10개 범위를 넘었습니다.")
        return self


class NewFactor(Schema):
    direction: Literal["favorable", "adverse", "neutral"]
    claim: Text
    fact_ids: list[FactId] = Field(min_length=1, max_length=12)
    major_constraint: bool = False


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
        if self.selection.basis == "outside_scope" and (
            self.status != "unknown" or self.review_state != "unreviewed"
        ):
            raise ValueError("검토 대상 밖은 판단 미검토입니다.")
        return self


class ReviewIssue(Schema):
    issue_id: Text
    industry_code: IndustryCode | None = None
    target: Literal["fact", "score", "L", "claim", "condition"]
    kind: Literal[
        "factual_error", "duplicate_score", "missing_evidence", "scope_mismatch", "action_condition"
    ]
    comment: Text
    fact_ids: list[FactId] = Field(default_factory=list, max_length=3)
    suggested_check: Text
    blocking: bool


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
    L_records: list[LRecord] = Field(default_factory=list, max_length=12)


class SubmitDraftInput(Schema):
    phase: Literal["draft", "final"]
    report: ReportProposal
    review_resolutions: list[ReviewResolution] = Field(default_factory=list, max_length=16)


class SubmitReviewInput(Schema):
    draft_id: Text
    verdict: Literal["agree", "conditional", "oppose"]
    issues: list[ReviewIssue] = Field(max_length=4)


class ScorecardResult(Schema):
    scorecards: list[Scorecard] = Field(default_factory=list, max_length=5)
    summaries: list[ScorecardSummary] = Field(default_factory=list, max_length=32)
    next_cursor: Text | None = None


class FactsResult(Schema):
    facts: list[FactView] = Field(max_length=32)
    provenance_refs: list[Text] = Field(default_factory=list)
    next_cursor: Text | None = None


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


class RemainingBudget(Schema):
    model_calls: Annotated[int, Field(ge=0, le=40)] = 40
    tool_calls: Annotated[int, Field(ge=0, le=40)] = 40
    input_tokens: Annotated[int, Field(ge=0, le=400000)] = 400000
    output_tokens: Annotated[int, Field(ge=0, le=60000)] = 60000
    active_seconds: Annotated[float, Field(ge=0, le=600)] = 600.0


class FinalCandidate(ScorecardSummary):
    industry_name: Text
    reasons_segments: list[FactSegment]
    risks_segments: list[FactSegment] = Field(default_factory=list)
    confirmation_conditions_segments: list[FactSegment] = Field(default_factory=list)
    fact_ids: list[FactId] = Field(default_factory=list)
    review_state: Literal["reviewed", "unreviewed"]


class EvaluatorReview(Schema):
    actor: EvaluatorActor
    status: Literal["completed", "failed"]
    review_id: Text | None = None
    verdict: Literal["agree", "conditional", "oppose"] | None = None
    issues: list[ReviewIssue] = Field(max_length=4)
    error_code: ErrorCode | None = None

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
    "submit_draft": SubmitDraftInput,
    "submit_review": SubmitReviewInput,
}
_TOOL_DESCRIPTIONS = {
    "get_scorecard": "업종별 코드 점수·문항 상태·근거를 먼저 조회합니다. 상세는 최대 5개입니다.",
    "get_facts": "fact_ids 또는 업종·출처·지표 중 한 방식으로 계산 사실을 조회합니다.",
    "query_raw": "승인 뷰 SELECT로 원문을 최대 50행 확인합니다. 쓰기·집계 인용은 금지합니다.",
    "map_search": "업종 또는 시설 하나를 검색해 장소·카테고리·거리·규칙 일치 상태를 받습니다.",
    "check_regulation": "현재 좌표의 교육환경보호구역과 업종 제한을 확인합니다.",
    "ask_advisor": "애매한 질문과 fact_id 근거로 자문만 받습니다. 최종 판단은 decision이 합니다.",
    "ask_user": "임대인에게 미확인 상가 조건을 최대 3개 질문합니다.",
    "submit_draft": "fact 슬롯·L 근거로 초안/최종을 제출합니다. 점수·숫자 복사는 금지합니다.",
    "submit_review": "초안의 사실·L 중복·확인 조건을 검토해 최대 4개 지적을 제출합니다.",
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
    """Chat Completions에 전달할 9개 function 정의입니다. 역할 권한 필터는 PR4 범위입니다."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": _TOOL_DESCRIPTIONS[name],
                "strict": False,
                "parameters": _function_schema(model.model_json_schema()),
            },
        }
        for name, model in TOOL_INPUTS.items()
    ]
