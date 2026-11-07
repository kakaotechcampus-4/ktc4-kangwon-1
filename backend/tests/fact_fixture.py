import json

from app.domain.facts import FactRecord


def fact_record(
    fact_id="f",
    *,
    metric="metric",
    source="source",
    unit="",
    value=None,
    status="observed",
    citable=True,
    industry_code=None,
    period="기간",
    spatial_scope=None,
    value_text=None,
    spatial_key=None,
    calc_version="v",
    local_lineage=False,
):
    return FactRecord(
        fact_id=fact_id,
        industry_code=industry_code,
        source=source,
        metric=metric,
        unit=unit,
        period=period,
        status=status,
        citable=citable,
        calc_version=calc_version,
        local_lineage=local_lineage,
        value_text=value_text if value_text is not None else json.dumps(value, ensure_ascii=False),
        spatial_key=spatial_key if spatial_key is not None else json.dumps(spatial_scope or {}),
    )
