"""AI 도구의 입력·응답 계약과 OpenAI 호환 function 정의입니다."""

from copy import deepcopy
from typing import Annotated, Any, Literal, Self, get_args

from pydantic import Field, JsonValue, model_validator

from app.domain.contracts import (
    CodeItemCalculation,
    FactId,
    FactView,
    Grade,
    IndustryCode,
    ItemStatus,
    MapSearchInput,
    Metric,
    ReportProposal,
    ReviewIssue,
    ReviewResolution,
    ScorecardSummary,
    ScoreItemId,
    Source,
    UserQuestion,
)
from app.domain.schema_types import Schema, Text

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


class ScoreItem(Schema):
    item: ScoreItemId
    status: ItemStatus
    grade: Grade | None
    points: Annotated[float, Field(ge=0, le=15)] | None
    fact_ids: list[FactId] = Field(max_length=32)
    scoring: CodeItemCalculation | None = None

    @model_validator(mode="after")
    def check_observation(self) -> Self:
        if self.status == "observed":
            if self.grade is None or self.points is None or not self.fact_ids:
                raise ValueError("관측 문항에는 등급·점수·근거가 필요합니다.")
        elif self.grade is not None or self.points is not None:
            raise ValueError("미확인·미적용 문항에는 등급·점수를 채우지 않습니다.")
        if self.scoring and self.status == "not_applicable" and self.scoring.points != 0:
            raise ValueError("미적용 항목에 보완 기여를 넣을 수 없습니다.")
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


class CheckRegulationInput(Schema):
    pass


class AskAdvisorInput(Schema):
    question: Annotated[str, Field(min_length=1, max_length=800)]
    fact_ids: list[FactId] = Field(min_length=1, max_length=12)
    industry_codes: list[IndustryCode] | None = Field(default=None, min_length=1, max_length=3)


class AskUserInput(Schema):
    questions: list[UserQuestion] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        if len({q.field for q in self.questions}) != len(self.questions):
            raise ValueError("질문 항목이 중복됩니다.")
        return self


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
