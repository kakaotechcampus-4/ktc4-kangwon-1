"""계산·지도·질문 공통 기반 타입입니다."""

from typing import Annotated, ClassVar, Literal, Self, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    model_validator,
)

from app.industries import lookup

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


class IndustryRow(Schema):
    industry_key: ClassVar[str] = "industry_code"
    name_key: ClassVar[str | None] = None

    @model_validator(mode="after")
    def check_industry(self) -> Self:
        code = getattr(self, self.industry_key)
        industry = lookup.find(code) if isinstance(code, str) else None
        if industry is None:
            raise ValueError("공통 업종표에 없는 업종 코드입니다.")
        name = getattr(self, self.name_key) if self.name_key else None
        named = lookup.find_by_name(name) if isinstance(name, str) else None
        if name is not None and (named is None or named.code != industry.code):
            raise ValueError("업종 코드와 명칭이 일치하지 않습니다.")
        return self

    @property
    def owner_code(self) -> str:
        return str(getattr(self, self.industry_key))


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


QuestionField = Literal[
    "floor", "exclusive_area", "space_condition", "existing_facilities", "industry_preferences"
]


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
    queries: list[MapQuery] = Field(min_length=1, max_length=8)

    def unique_queries(self) -> list[MapQuery]:
        seen = set()
        result = []
        for query in self.queries:
            key = (query.kind, query.industry_code, query.facility_code, query.query)
            if key not in seen:
                result.append(query)
                seen.add(key)
        return result


MatchStatus = Literal["same", "different", "unclear"]


class MapQueryResult(Schema):
    request: MapQuery
    status: Literal["ok", "error"]
    method: Literal["keyword", "category"]
    category_code: FacilityCode | None = None
    total_count: Annotated[int, Field(ge=0)] | None = None
    place_ids: list[Text] = Field(default_factory=list)
    has_more: bool | None = None
    error: Text | None = None
    # 질문 업종 기준 장소별 동종 판단. 시설 검색·옛 자료는 비어 있습니다.
    matches: dict[Text, MatchStatus] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_result(self) -> Self:
        if not self.matches.keys() <= set(self.place_ids) or (
            self.matches and (self.request.kind == "infrastructure" or self.status == "error")
        ):
            raise ValueError("동종 판단은 성공한 업종 검색의 장소만 참조해야 합니다.")
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
    # mapping_status·industry_code는 2026-10 이전 관측 호환용입니다.
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
        for query in self.queries.values():
            for place_id, match in query.matches.items():
                if match == "same" and query.request.industry_code:
                    expected.setdefault(query.request.industry_code, set()).add(place_id)
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
        if not 1 <= len(queries) <= 8 or set(queries) != {
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
            or any("unclear" in q.matches.values() for q in queries.values())
        ):
            raise ValueError("불완전한 지도 관측은 partial이어야 합니다.")
        return self
