"""팀 간 연결에 필요한 입력과 출력을 정의합니다."""

from typing import Annotated, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


# 공통 기본 타입과 검증 규칙
AgentId = Literal["floating_population", "business_lifecycle", "commercial_area"]
AGENT_IDS = get_args(AgentId)
Text = Annotated[str, Field(min_length=1)]
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
                raise ValueError("자료 없음 분석은 분석 범위, 빈 자료와 오류 없는 상태를 전달해야 합니다.")
        elif self.scope is None or not self.data or self.error:
            raise ValueError("사용 가능한 분석에는 지역, 기준 기간과 자료가 필요합니다.")
        return self


# 중재·최종 점수 에이전트 입력
class DecisionRequest(Schema):
    request_id: Text
    address: Text
    analyses: list[AgentAnalysis] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def check_unique_sources(self) -> Self:
        ids = [analysis.agent_id for analysis in self.analyses]
        if len(ids) != len(set(ids)):
            raise ValueError("같은 에이전트의 분석을 중복으로 전달할 수 없습니다.")
        if any(analysis.request_id != self.request_id for analysis in self.analyses):
            raise ValueError("다른 요청의 분석 결과를 함께 전달할 수 없습니다.")
        return self


class Evidence(Schema):
    agent_id: AgentId
    path: Text = Field(description="해당 분석 자료 안의 필드 경로. 예: /industries/0")


class Category(Schema):
    major: Text
    middle: Text


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
    status: Literal["ok", "partial", "no_data"]
    source_analyses: list[AgentAnalysis]
