from typing import ClassVar

from pydantic import Field, JsonValue

from app.schemas import IndustryRow, Schema, Text


class LifecycleIndustry(IndustryRow):
    industry_key: ClassVar[str] = "industry_id"
    name_key: ClassVar[str | None] = "industry_name"

    industry_id: Text
    industry_name: Text
    score: float | None
    type: Text
    citable: dict[str, bool] | None = None
    confidence: Text
    data_available: bool
    score_available: bool
    data_status: str | None = None
    data_complete: bool
    metrics: dict[str, JsonValue] = Field(default_factory=dict)
    source_coverage: dict[str, JsonValue] | None = None
    evidence: list[JsonValue] = Field(default_factory=list)
    warning: str | None = None


class QuarterIndustry(IndustryRow):
    industry_key: ClassVar[str] = "industry_id"

    industry_id: Text
    store_counts: list[float | None]
    opened_counts: list[float | None]
    closed_counts: list[float | None]
    close_rates: list[float | None]
    confidence: Text


class SupplementQuarters(Schema):
    area_code: Text
    quarters: list[Text]
    count_unit: Text
    rate_unit: Text
    industries: list[QuarterIndustry]
    unsupported_industry_ids: list[Text] = Field(default_factory=list)
    missing_industry_ids: list[Text] = Field(default_factory=list)
    note: Text
    retrieved_at: Text


class BusinessLifecycleData(Schema):
    summary: str = ""
    metadata: dict[str, JsonValue]
    coverage: dict[str, JsonValue]
    taxonomy: dict[str, JsonValue]
    scoring_method: dict[str, JsonValue]
    industries: list[LifecycleIndustry]
    supplement_quarters: SupplementQuarters | None = None
