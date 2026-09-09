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


class Diversity(Schema):
    hhi_major: float
    hhi_middle: float
    effective_categories: float


class RestaurantDensity(Schema):
    value: float
    squared: float
    unit: Literal["stores_per_km2"]
    store_count: int


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


class Summary(Schema):
    radius_notes: list[RadiusNote] = Field(default_factory=list)
    overall: Text | None = None
    concentration: Text | None = None


class FranchiseByMiddle(Schema):
    code: Text
    name: Text
    count: int
    ratio: float


class Franchise(Schema):
    count: int
    ratio: float
    by_middle: list[FranchiseByMiddle] = Field(default_factory=list)
    method: Literal["brand_name_match"]
    confidence: Literal["low", "medium", "high"]


class DistrictBaseline(Schema):
    signgu_code: Text
    signgu_name: Text | None = None
    store_total: int


class LqBaseline(Schema):
    requested_radius_m: int
    applied_radius_m: int | None = None
    store_total: int | None = None


class CommercialAreaData(Schema):
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
    summary: Summary | None = None
    summary_text: Text | None = None


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
