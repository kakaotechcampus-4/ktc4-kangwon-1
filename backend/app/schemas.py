"""팀 간 연결에 필요한 입력과 출력을 정의합니다."""

from typing import Annotated, Any, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, model_validator

from app.industries import lookup

# 공통 기본 타입과 검증 규칙
AgentId = Literal["floating_population", "business_lifecycle", "commercial_area"]
AGENT_IDS = get_args(AgentId)
Text = Annotated[str, Field(min_length=1)]
RadiusMeters = Annotated[int, Field(strict=True, gt=0)]
DEFAULT_RADIUS_M = 500
validate_radius = TypeAdapter(RadiusMeters).validate_python
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]


class Schema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
        revalidate_instances="always",
    )


# 유동인구·개폐업·상권 에이전트 공통 입력
class Scope(Schema):
    area: Text
    period: Text


class Site(Schema):
    input_address: Text
    road_address: Text | None = None
    jibun_address: Text | None = None
    detail_address: Text | None = None
    latitude: Latitude
    longitude: Longitude

    @model_validator(mode="after")
    def check_base_address(self) -> Self:
        if not self.road_address and not self.jibun_address:
            raise ValueError("도로명주소 또는 지번주소가 필요합니다.")
        return self


class AnalysisTask(Schema):
    """세 분석 에이전트에 공통으로 전달하는 위치 정보입니다."""

    request_id: Text
    site: Site
    radius_m: RadiusMeters = DEFAULT_RADIUS_M


# 유동인구·개폐업·상권 에이전트 공통 출력
class AgentError(Schema):
    code: Text
    message: Text


class AgentAnalysis(Schema):
    request_id: Text
    agent_id: AgentId
    status: Literal["ok", "partial", "no_data", "error"]
    scope: Scope | None = None
    data: dict[str, JsonValue] = Field(default_factory=dict)
    error: AgentError | None = None
    warnings: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_status(self) -> Self:
        if self.status == "error":
            if not self.error or self.data:
                raise ValueError("실패한 분석은 오류 설명과 빈 자료를 전달해야 합니다.")
        elif self.status == "no_data":
            if self.scope is None or self.data or self.error:
                raise ValueError(
                    "자료 없음 분석은 분석 범위, 빈 자료와 오류 없는 상태를 전달해야 합니다."
                )
        elif self.scope is None or not self.data or self.error:
            raise ValueError("사용 가능한 분석에는 지역, 기준 기간과 자료가 필요합니다.")
        return self


class SupplementOperation(Schema):
    """코드에 등록된 보완 작업의 공개 설명입니다."""

    agent_id: AgentId
    operation: Text
    description: Text


class SupplementRequest(Schema):
    agent_id: AgentId
    operation: Text
    decision_question: Text
    missing_information: Text
    why_needed: Text
    expected_impact: Text


class SupplementPlan(Schema):
    action: Literal["supplement"]
    requests: list[SupplementRequest] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def check_targets(self) -> Self:
        ids = [item.agent_id for item in self.requests]
        if len(ids) != len(set(ids)):
            raise ValueError("한 보완 라운드에서 에이전트별 작업은 하나만 허용합니다.")
        return self


class SupplementEvent(Schema):
    request_id: Text
    request: SupplementRequest
    status: Literal["requested", "succeeded", "failed", "rejected"]
    message: Text
    adopted: bool = False
    analysis: AgentAnalysis | None = None

    @model_validator(mode="after")
    def check_analysis(self) -> Self:
        if self.analysis is not None:
            if (
                self.analysis.request_id != self.request_id
                or self.analysis.agent_id != self.request.agent_id
            ):
                raise ValueError("보완 결과 식별자가 요청과 다릅니다.")
        if self.adopted and (self.status != "succeeded" or self.analysis is None):
            raise ValueError("성공한 분석 결과만 채택할 수 있습니다.")
        if (
            self.adopted
            and self.analysis is not None
            and self.analysis.status not in {"ok", "partial"}
        ):
            raise ValueError("사용 가능한 분석 결과만 채택할 수 있습니다.")
        if self.status in {"requested", "rejected"} and self.analysis is not None:
            raise ValueError("실행 전 이벤트에는 분석 결과가 없습니다.")
        return self


# 임대인에게 선택적으로 요청하는 정보
QuestionField = Literal[
    "floor", "exclusive_area", "space_condition", "existing_facilities", "industry_preferences"
]
QUESTION_FIELDS = get_args(QuestionField)


class LandlordQuestion(Schema):
    field: QuestionField
    text: Text
    why_needed: Text
    expected_impact: Text


class QuestionPlan(Schema):
    action: Literal["ask_user"]
    questions: list[LandlordQuestion] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        if len({q.field for q in self.questions}) != len(self.questions):
            raise ValueError("같은 항목을 중복 질문할 수 없습니다.")
        return self


class WaitingForInput(Schema):
    status: Literal["waiting_for_input"] = "waiting_for_input"
    request_id: Text
    question_set_id: Text
    questions: list[LandlordQuestion] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def check_questions(self) -> Self:
        QuestionPlan(action="ask_user", questions=self.questions)
        return self


class LandlordAnswer(Schema):
    field: QuestionField
    status: Literal["answered", "unknown", "skipped"]
    value: Annotated[str, Field(min_length=1, max_length=1000)] | None = None

    @model_validator(mode="after")
    def check_value(self) -> Self:
        if (self.status == "answered") != (self.value is not None):
            raise ValueError("답변 완료인 항목에만 답변 내용을 작성하세요.")
        return self


class AnswerSubmission(Schema):
    request_id: Text
    question_set_id: Text
    answers: list[LandlordAnswer] = Field(max_length=3)

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        if len({a.field for a in self.answers}) != len(self.answers):
            raise ValueError("같은 항목에 중복 답변할 수 없습니다.")
        return self


def normalize_answers(waiting: WaitingForInput, submission: AnswerSubmission) -> AnswerSubmission:
    """누락 답변은 건너뛰기로 확정하고 순서와 무관하게 같은 제출로 비교합니다."""
    waiting = WaitingForInput.model_validate(waiting)
    submission = AnswerSubmission.model_validate(submission)
    if (waiting.request_id, waiting.question_set_id) != (
        submission.request_id,
        submission.question_set_id,
    ):
        raise ValueError("질문과 답변의 식별자가 일치하지 않습니다.")
    fields = {q.field for q in waiting.questions}
    answers = {a.field: a for a in submission.answers}
    if not set(answers) <= fields:
        raise ValueError("요청하지 않은 항목에는 답변할 수 없습니다.")
    return AnswerSubmission(
        request_id=waiting.request_id,
        question_set_id=waiting.question_set_id,
        answers=[answers.get(f, LandlordAnswer(field=f, status="skipped")) for f in sorted(fields)],
    )


class QuestionSnapshot(Schema):
    """질문 경계의 내부 저장 계약입니다. 분석 본문은 저장된 차수로 참조합니다."""

    version: Literal[1] = 1
    task: AnalysisTask
    waiting: WaitingForInput
    source_attempts: dict[AgentId, Annotated[int, Field(strict=True, gt=0)]]
    supplement_done: bool
    feedback: list[Text]

    @model_validator(mode="after")
    def check_references(self) -> Self:
        if self.task.request_id != self.waiting.request_id:
            raise ValueError("작업과 질문의 요청 ID가 다릅니다.")
        if set(self.source_attempts) != set(AGENT_IDS):
            raise ValueError("세 분석의 실행 차수가 필요합니다.")
        return self


# 지도 요청·관측은 세 분석의 실행 계약과 분리합니다.
FacilityCode = Literal[
    "MT1",
    "CS2",
    "PS3",
    "SC4",
    "AC5",
    "PK6",
    "OL7",
    "SW8",
    "BK9",
    "CT1",
    "AG2",
    "PO3",
    "AT4",
    "AD5",
    "FD6",
    "CE7",
    "HP8",
    "PM9",
]


class MapQuery(Schema):
    kind: Literal["industry", "infrastructure"]
    industry_code: Text | None = None
    facility_code: FacilityCode | None = None
    query: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    why_needed: Text
    expected_impact: Text

    @model_validator(mode="after")
    def check_target(self) -> Self:
        from app.industries.lookup import find

        if self.kind == "industry":
            if (
                not self.industry_code
                or not find(self.industry_code)
                or not self.query
                or self.facility_code
            ):
                raise ValueError("유효한 업종 코드와 검색 표현만 필요합니다.")
        elif not self.facility_code or self.industry_code or self.query:
            raise ValueError("시설 조회에는 지원 시설 코드만 필요합니다.")
        return self


class MapLookupPlan(Schema):
    action: Literal["map_lookup"]
    queries: list[MapQuery] = Field(min_length=1, max_length=5)

    def unique_queries(self) -> list[MapQuery]:
        seen = set()
        result = []
        for query in self.queries:
            key = (query.kind, query.industry_code, query.facility_code, query.query)
            if key not in seen:
                result.append(query)
                seen.add(key)
        return result


class MapQueryResult(Schema):
    request: MapQuery
    status: Literal["ok", "error"]
    method: Literal["keyword", "category"]
    category_code: FacilityCode | None = None
    total_count: Annotated[int, Field(ge=0)] | None = None
    place_ids: list[Text] = Field(default_factory=list)
    has_more: bool | None = None
    error: Text | None = None

    @model_validator(mode="after")
    def check_result(self) -> Self:
        if self.status == "error":
            if not self.error or self.total_count is not None or self.place_ids:
                raise ValueError("실패한 검색은 건수·장소 대신 오류를 반환합니다.")
        elif self.error or self.total_count is None:
            raise ValueError("성공한 검색에는 건수가 필요합니다.")
        if (self.method == "category") != (self.category_code is not None):
            raise ValueError("실제 조회 방식과 카테고리가 다릅니다.")
        if len(set(self.place_ids)) != len(self.place_ids):
            raise ValueError("검색 내 장소가 중복되었습니다.")
        return self


class MapPlace(Schema):
    name: Text
    category_name: str
    category_code: str = ""
    distance_m: Annotated[int, Field(ge=0)] | None = None
    place_url: Text | None = None
    mapping_status: Literal["mapped", "ambiguous", "unmapped", "not_applicable"] = "not_applicable"
    industry_code: Text | None = None
    mapping_method: Literal["llm"] | None = None
    reason: Text | None = None

    @model_validator(mode="after")
    def check_mapping(self) -> Self:
        from app.industries.lookup import find

        if self.mapping_status == "mapped":
            if (
                not self.industry_code
                or not find(self.industry_code)
                or self.mapping_method != "llm"
            ):
                raise ValueError("매핑된 장소에는 유효한 업종 코드와 방법이 필요합니다.")
        elif self.industry_code is not None:
            raise ValueError("미확정 장소에 업종 코드를 지정할 수 없습니다.")
        return self


class MapIndustry(Schema):
    name: Text
    major: Text
    place_ids: list[Text]
    sampled_count: int = Field(ge=1)


class MapData(Schema):
    queries: dict[Text, MapQueryResult]
    places: dict[Text, MapPlace] = Field(default_factory=dict)
    industries: dict[Text, MapIndustry] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_links(self) -> Self:
        from app.industries.lookup import find

        referenced = {p for q in self.queries.values() for p in q.place_ids}
        if referenced != set(self.places):
            raise ValueError("검색과 장소의 참조가 다릅니다.")
        expected: dict[str, set[str]] = {}
        for place_id, place in self.places.items():
            if place.industry_code:
                expected.setdefault(place.industry_code, set()).add(place_id)
        if set(expected) != set(self.industries):
            raise ValueError("매핑 장소와 업종 집계가 다릅니다.")
        for code, group in self.industries.items():
            master = find(code)
            if (
                master is None
                or group.name != master.name
                or group.major != master.major_name
                or set(group.place_ids) != expected[code]
                or len(group.place_ids) != len(expected[code])
                or group.sampled_count != len(expected[code])
            ):
                raise ValueError("업종 명칭 또는 표본 집계가 일치하지 않습니다.")
        return self


class MapObservation(Schema):
    request_id: Text
    observation_id: Text
    site: Site
    radius_m: RadiusMeters
    queried_at: Text
    master_version: Text
    status: Literal["ok", "partial", "no_data", "error"]
    data: MapData
    warnings: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_observation(self) -> Self:
        from datetime import datetime, timedelta

        stamp = datetime.fromisoformat(self.queried_at)
        if stamp.utcoffset() != timedelta(0):
            raise ValueError("지도 조회 시각은 UTC여야 합니다.")
        queries = self.data.queries
        if not 1 <= len(queries) <= 5 or set(queries) != {
            f"q{i}" for i in range(1, len(queries) + 1)
        }:
            raise ValueError("지도 검색 식별자가 올바르지 않습니다.")
        success = [q for q in queries.values() if q.status == "ok"]
        if (not success) != (self.status == "error"):
            raise ValueError("검색 성공 여부와 관측 상태가 다릅니다.")
        if self.status == "no_data" and (
            len(success) != len(queries)
            or self.data.places
            or any(q.total_count != 0 for q in success)
        ):
            raise ValueError("자료 없음은 모든 검색이 정상 0건이어야 합니다.")
        if self.status == "ok" and (
            len(success) != len(queries)
            or not any(q.total_count for q in success)
            or any(p.mapping_status in {"unmapped", "ambiguous"} for p in self.data.places.values())
        ):
            raise ValueError("불완전한 지도 관측은 partial이어야 합니다.")
        return self


# 최종판단 에이전트 입력
class DecisionRequest(Schema):
    request_id: Text
    address: Text
    analyses: list[AgentAnalysis] = Field(min_length=1, max_length=3)
    map_observation: MapObservation | None = None

    @model_validator(mode="after")
    def check_unique_sources(self) -> Self:
        if self.map_observation and self.map_observation.request_id != self.request_id:
            raise ValueError("지도 관측의 요청 ID가 다릅니다.")
        ids = [analysis.agent_id for analysis in self.analyses]
        if len(ids) != len(set(ids)):
            raise ValueError("같은 에이전트의 분석을 중복으로 전달할 수 없습니다.")
        if any(analysis.request_id != self.request_id for analysis in self.analyses):
            raise ValueError("다른 요청의 분석 결과를 함께 전달할 수 없습니다.")
        return self


class Evidence(Schema):
    agent_id: AgentId | Literal["map_analysis"]
    path: Text = Field(description="해당 분석 자료 안의 필드 경로. 예: /industries/0")


class Category(Schema):
    code: Text | None = None
    major: Text
    middle: Text

    @model_validator(mode="before")
    @classmethod
    def resolve_code(cls, value: Any) -> Any:
        """코드 입력은 공식명을 채우고, 과거 이름 입력도 유지합니다."""
        if not isinstance(value, dict):
            return value
        data = dict(value)
        code = data.get("code")
        if code is not None:
            industry = lookup.find(code) if isinstance(code, str) else None
            if industry is None:
                raise ValueError("공통 업종표에 없는 코드입니다.")
            for key, expected in (("major", industry.major_name), ("middle", industry.name)):
                if key in data and data[key] != expected:
                    raise ValueError("업종 코드와 명칭이 일치하지 않습니다.")
                data[key] = expected
        elif isinstance(data.get("middle"), str):
            industry = lookup.find_by_name(data["middle"])
            if industry and data.get("major") == industry.major_name:
                data.update(code=industry.code, middle=industry.name)
        return data


class IndustryAssessment(Schema):
    category: Category
    score: int = Field(ge=0, le=100, description="적합성 판단 점수이며 성공 확률이 아님")
    reasons: list[Text] = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)
    risks: list[Text]


# 중재 에이전트가 모델에서 받는 판단 내용
class DecisionContent(Schema):
    status: Literal["ok", "no_data"]
    summary: Text
    recommendations: list[IndustryAssessment] = Field(max_length=5)
    not_recommended: list[IndustryAssessment] = Field(max_length=5)
    limitations: list[Text]

    @model_validator(mode="after")
    def check_decisions(self) -> Self:
        categories = [
            (item.category.major.casefold(), item.category.middle.casefold())
            for item in self.recommendations + self.not_recommended
        ]
        if len(categories) != len(set(categories)):
            raise ValueError("같은 중분류 업종을 여러 번 판단할 수 없습니다.")
        if self.status == "no_data":
            if categories or not self.limitations:
                raise ValueError("판단 보류 시 업종 목록을 비우고 부족한 자료를 설명해야 합니다.")
        elif not categories:
            raise ValueError("판단한 업종이 없으면 자료 부족 상태로 반환해야 합니다.")
        return self


# 리포트 에이전트에 전달하는 중재 에이전트 최종 출력
class DecisionResult(DecisionContent):
    schema_version: Literal["1.0"]
    agent_id: Literal["decision"]
    request_id: Text
    address: Text
    # 중재 자체는 ok/no_data만 내지만, 입력 분석이 일부 빠지면 리포트에는 partial로 나갑니다.
    status: Literal["ok", "partial", "no_data"]  # type: ignore[assignment]
    source_analyses: list[AgentAnalysis]
    map_observation: MapObservation | None = None
