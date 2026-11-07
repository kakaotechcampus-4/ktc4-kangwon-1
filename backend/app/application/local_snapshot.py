"""로컬 계산 자료를 기존 채점·fact 저장기에 넘깁니다."""

import json

from app.application.facts import register_fact
from app.application.ports.market import market
from app.application.ports.storage import open_stores, storage
from app.application.snapshot import (
    persist_input_facts,
    persist_report,
    persist_space_requirements,
    snapshot_config,
)
from app.domain.scoring import evaluate

YEAR_QUARTERS = 4


def metric_periods(quarters):
    lifecycle = sorted(set(quarters.get("business_lifecycle", [])))
    if len(lifecycle) < YEAR_QUARTERS:
        return {}
    recent = f"{lifecycle[-YEAR_QUARTERS]}~{lifecycle[-1]}"
    return {
        "business_lifecycle": {
            "recent_year_close_rate": recent,
            "close_rate_ratio": recent,
            "oldest_year_close_rate": f"{lifecycle[0]}~{lifecycle[YEAR_QUARTERS - 1]}",
        }
    }


def persist_local(task, scope, adapter, data=None, observations=None):
    persist_space_requirements(scope)
    profiles, hashes, _ = snapshot_config(scope, local=True)
    data = data if data is not None else adapter.analyze(task)
    if observations is not None:
        data = (
            data
            | observations
            | {"limitations": data.get("limitations", []) + observations.get("limitations", [])}
        )
    storage().provenance.save_snapshot(scope, adapter, task, hashes, data)
    periods = {}
    for version in adapter.versions:
        periods.setdefault(market().source_names[version["source"]], []).append(version["quarter"])
    metadata = {
        "local_snapshot": scope.snapshot_id,
        "periods": {
            key: "~".join(sorted(values)[:: max(1, len(values) - 1)])
            for key, values in periods.items()
        },
        "metric_periods": metric_periods(periods),
    }
    persist_input_facts(scope, data, {}, [], metadata)
    report = evaluate(data, profile_rows=profiles)
    with open_stores(scope.path) as st:
        map_rows = st.raw.map_row_ids(scope.request_id, scope.snapshot_id)
    score_id = persist_report(scope, report, {"map": [row[0] for row in map_rows]}, [], metadata)
    return data, report, score_id


def register_cell(
    scope,
    source,
    version_id,
    row_key,
    column,
    *,
    metric,
    unit,
    expected_value=None,
    adapter=None,
    stores=None,
):
    adapter = adapter if adapter is not None else storage().provenance.validate_snapshot(scope)
    if adapter is None:
        raise ValueError("로컬 스냅샷 없음")
    if not any(v["source"] == source and v["version_id"] == version_id for v in adapter.versions):
        raise ValueError("다른 버전의 직접 셀")
    row = adapter.cell_row(source, version_id, row_key)
    if row is None:
        raise ValueError("원문 행 없음")
    raw = dict(zip(json.loads(row[1]), json.loads(row[0]), strict=True))
    if column not in raw or raw[column] is None:
        raise ValueError("원문 열 없음")
    if expected_value is not None and raw[column] != expected_value:
        raise ValueError("SQL 반환값과 원문 셀 값 불일치")
    return register_fact(
        scope,
        industry_code=row[2],
        source=market().source_names[source],
        metric=metric,
        value=raw[column],
        unit=unit,
        status="observed",
        period=str(
            raw.get("STDR_YYQU_CD")
            or next(v["quarter"] for v in adapter.versions if v["version_id"] == version_id)
        ),
        row_ids=[],
        comparison={"input_versions": {"local_snapshot": scope.snapshot_id}},
        local_cell={"version_id": version_id, "row_key": row_key, "column": column},
        stores=stores,
    )
