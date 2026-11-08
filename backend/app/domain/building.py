from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# 화면의 오수정화시설 선택지입니다(SEWAGE_OPTIONS에서 사용자 몫인 '모름'만 뺌).
SewageMethod = Literal["하수종말처리장 연결", "정화조", "오수처리시설"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BuildingTitle(Model):
    """표제부 한 동입니다."""

    dong_name: str | None = Field(description="동 이름. 한 지번에 건물이 여럿일 때 구분합니다.")
    building_name: str | None
    main_use: str | None = Field(description="주용도. 예: 제2종근린생활시설")
    ground_floors: int | None
    underground_floors: int | None
    total_area_m2: float | None = Field(description="연면적(㎡)")
    parking_spaces: int | None = Field(
        description="주차 대수. 옥내·옥외 기계식·자주식 합. 넷 다 비어 있으면 null"
    )


class FloorOverview(Model):
    """층별개요 한 행입니다. 한 층에 용도가 여럿이면 여러 행입니다."""

    dong_name: str | None
    floor: str | None = Field(description="예: 4층, 지하 1층")
    use: str | None = Field(description="용도(대장 주용도코드명). 예: 일반음식점")
    use_detail: str | None = Field(description="기타용도(대장 원문). 예: 제2종근린생활시설")
    area_m2: float | None


class Unit(Model):
    """호실 하나입니다. 면적은 전유 부분만 더한 값입니다."""

    dong_name: str | None
    unit_name: str | None = Field(description="호수. 예: 401호")
    floor: str | None = Field(description="예: 4층, 지하 1층")
    use: str | None = Field(description="용도(대장 주용도코드명). 예: 학원")
    use_detail: str | None = Field(description="기타용도(대장 원문). 예: 교육연구시설(학원)")
    area_m2: float | None = Field(description="전용면적(㎡)")


class SewageFacility(Model):
    """오수정화시설 한 건입니다."""

    method: SewageMethod | None = Field(
        description="화면 선택지로 맞춘 처리 방식. 맞출 수 없는 형식이면 null"
    )
    method_name: str | None = Field(
        description="대장 원문 형식(형식코드명, 비어 있으면 기타형식). 예: 접촉폭기방법"
    )


class BuildingRegistry(Model):
    """목록이 null이면 그 항목 조회가 실패한 것이고, []이면 등록된 행이 없는 것입니다."""

    road_address: str | None
    jibun_address: str | None
    titles: list[BuildingTitle] | None = Field(
        description="연면적이 큰 건물부터. 한 지번에 건물이 여럿이면 titles[0]이 대표 건물"
    )
    floors: list[FloorOverview] | None
    units: list[Unit] | None
    sewage: list[SewageFacility] | None
