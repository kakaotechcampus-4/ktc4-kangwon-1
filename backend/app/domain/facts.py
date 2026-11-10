import json
from dataclasses import dataclass


@dataclass
class FactRecord:
    fact_id: str
    industry_code: str | None
    source: str
    metric: str
    unit: str
    period: str
    status: str
    citable: bool
    calc_version: str
    local_lineage: bool
    value_text: str
    spatial_key: str

    @property
    def value(self):
        return json.loads(self.value_text)

    @property
    def spatial_scope(self):
        return json.loads(self.spatial_key)


METRICS = {
    "D1": ("pattern_fit_index", "배수", "floating_population"),
    "D2": ("day_fit_index", "배수", "floating_population"),
    "D3": ("target_age_index", "배수", "floating_population"),
    "D4": ("yoy_change", "비율", "floating_population"),
    "C1": ("competition_index", "배수", "commercial_area"),
    "C4": ("distance_m", "m", "map"),
    "S1": ("close_rate_ratio", "배수", "business_lifecycle"),
    "S2": ("net_change_index", "배수", "business_lifecycle"),
    "S3": ("turnover_ratio", "배수", "business_lifecycle"),
    "S4": ("close_trend_ratio", "배수", "business_lifecycle"),
}


def fact_period(version, source, metric, default):
    return version.get("metric_periods", {}).get(source, {}).get(metric) or version.get(
        "periods", {}
    ).get(source, default)


CALC_VERSION = "rubric-v0.8-pr3-2"
ANSWER_UNIT = "임대인 답변"


def fact_identity(
    *,
    industry_code,
    source,
    metric,
    value,
    unit,
    status,
    period,
    row_ids,
    response_ids,
    comparison,
    local_cell,
    parent_fact_ids,
):
    identity = {
        "industry": industry_code,
        "source": source,
        "metric": metric,
        "value": value,
        "unit": unit,
        "status": status,
        "period": period,
        "rows": row_ids,
        "responses": sorted(response_ids),
        "comparison": comparison,
        "calc_version": CALC_VERSION,
        "local_cell": local_cell,
    }
    if parent_fact_ids:
        identity["parents"] = parent_fact_ids
    return identity


def is_citable(status, *, row_ids, response_ids, local, parent_fact_ids):
    return status == "observed" and bool(row_ids or response_ids or local or parent_fact_ids)
