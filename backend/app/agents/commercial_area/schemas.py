"""상권 경쟁 분석 결과의 자료 구조입니다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from app.schemas import Schema, Text


class MajorCategory(Schema):
    code: Text
    name: Text
    count: int
    share: float
    density_per_km2: float


class MiddleCategory(Schema):
    code: Text
    name: Text
    major_code: Text
    major_name: Text
    count: int
    share: float
    density_per_km2: float
    density_sq: float
    lq: float | None = None
    lq_district: float | None = None
    same_type_count: int
    diff_type_count: int
    marshallian: float
    jacobian: float
    # 누적 유인(Nelson 2원칙) — 같은 성격의 가게가 얼마나 모였고, 그 안이 얼마나 다양한가.
    # 두 값을 합쳐 점수로 만들지 않는다. 가중치를 정하는 순간 그게 판단이 된다.
    major_cluster_count: int
    major_cluster_diversity: float


class Diversity(Schema):
    hhi_major: float
    hhi_middle: float
    effective_categories: float


class RestaurantDensity(Schema):
    value: float
    squared: float
    unit: Literal["stores_per_km2"]
    store_count: int
    # 서울 상권 1,650곳 분포에서의 위치(0~100). 논문 임계값을 대신하는 값이라
    # 추정이 아니라 관측 분포 그 자체다. 서울 밖은 null.
    seoul_percentile: float | None = None


class CategoryRank(Schema):
    rank: int
    code: Text
    name: Text
    count: int
    density_per_km2: float
    note: Text


class SpecializationRank(Schema):
    rank: int
    code: Text
    name: Text
    count: int
    times_vs_surroundings: float
    note: Text


class SliceExplanations(Schema):
    store_total: Text
    top: Text
    bottom: Text
    concentration: Text
    specialization: Text


class RadiusSlice(Schema):
    radius_m: int
    store_total: int
    category_count: int
    absent_category_count: int
    top_by_count: list[CategoryRank] = Field(default_factory=list)
    bottom_by_count: list[CategoryRank] = Field(default_factory=list)
    top_by_concentration: list[CategoryRank] = Field(default_factory=list)
    top_by_specialization: list[SpecializationRank] = Field(default_factory=list)
    explanations: SliceExplanations


class RadiusNote(Schema):
    radius_m: int
    text: Text


class IndexNote(Schema):
    """지표 하나를 이 자리의 실제 값으로 풀어 쓴 문장.

    `path` 는 설명 대상 필드의 JSON Pointer 다. 리포트가 해당 숫자 옆에 캡션으로 붙일 수 있게
    함께 싣는다 — `by_radius[].explanations` 와 같은 쓰임이다.
    """

    path: Text
    label: Text
    text: Text


class Summary(Schema):
    radius_notes: list[RadiusNote] = Field(default_factory=list)
    overall: Text | None = None
    concentration: Text | None = None
    # 지표가 무슨 뜻인지 모르는 사람을 위한 풀이. 값이 없는 지표는 빠진다.
    index_notes: list[IndexNote] = Field(default_factory=list)


class FranchiseByMiddle(Schema):
    code: Text
    name: Text
    count: int
    ratio: float


class Franchise(Schema):
    count: int
    ratio: float
    independent_count: int
    independent_ratio: float
    by_middle: list[FranchiseByMiddle] = Field(default_factory=list)
    method: Literal["brand_name_match"]
    confidence: Literal["low", "medium", "high"]
    # 브랜드 목록의 기준 연도. 상가정보(분기)와 원천이 달라 따로 밝힌다.
    base_year: int | None = None


class DistrictBaseline(Schema):
    signgu_code: Text
    signgu_name: Text | None = None
    store_total: int


class LqBaseline(Schema):
    requested_radius_m: int
    applied_radius_m: int | None = None
    store_total: int | None = None


class TradeArea(Schema):
    """분석 반경과 겹치는 서울시 상권 하나.

    `kind` 가 LQ 해석의 전제다 — 같은 LQ 값이 발달상권과 골목상권에서 반대 뜻이 된다(B2).
    상권은 점이 아니라 구역이라 `distance_m` 만으로는 왜 걸렸는지 설명이 안 되므로
    크기(`area_m2`·`equivalent_radius_m`)를 함께 싣는다.
    """

    code: Text
    name: Text
    kind: Text | None = None  # 골목상권 · 발달상권 · 전통시장 · 관광특구
    signgu: Text | None = None
    distance_m: float
    area_m2: float
    equivalent_radius_m: float


class Source(Schema):
    name: Text
    url: Text
    license: Text
    period: Text


class CommercialAreaData(Schema):
    # 맨 앞에 둔다 — 결정 에이전트 프롬프트가 "필드 이름, 설명, 단위와 실제 값을 함께 읽는다"고
    # 명시하고 있어서, 숫자의 기준을 글로도 밝혀 두지 않으면 오독된다.
    description: Text
    radius_m: int
    store_total: int
    data_reference_date: Text | None = None
    by_major: list[MajorCategory] = Field(default_factory=list)
    by_middle: list[MiddleCategory] = Field(default_factory=list)
    by_radius: list[RadiusSlice] = Field(default_factory=list)
    diversity: Diversity
    restaurant_density: RestaurantDensity
    franchise: Franchise | None = None
    lq_baseline: LqBaseline
    district_baseline: DistrictBaseline | None = None
    district_specialization: list[SpecializationRank] = Field(default_factory=list)
    # 서울시 자료라 서울 밖에서는 빈 배열이다. 우리 에이전트는 전국을 받는다.
    trade_areas: list[TradeArea] = Field(default_factory=list)
    summary: Summary | None = None
    summary_text: Text | None = None
    # 공공누리 자료라 출처 표기가 의무다. 리포트가 하드코딩하지 않도록 함께 싣는다.
    sources: list[Source] = Field(default_factory=list)


@dataclass(frozen=True)
class Store:
    store_id: str
    name: str
    branch_name: str | None
    major_code: str
    major_name: str
    middle_code: str
    middle_name: str
    small_code: str | None
    small_name: str | None
    latitude: float | None
    longitude: float | None
    road_address: str | None
    district_code: str | None = None
    district_name: str | None = None


@dataclass(frozen=True)
class MiddleCode:
    code: str
    name: str
    major_code: str
    major_name: str
