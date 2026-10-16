"""로컬 계산 자료를 기존 채점·fact 저장기에 넘깁니다."""

import json

from app.agentic.facts import register_fact
from app.agentic.scoring import evaluate
from app.agentic.snapshot import (
    persist_input_facts,
    persist_report,
    persist_space_requirements,
    snapshot_config,
)
from app.db.connection import connect
from app.local_data.adapter import SOURCE_NAMES
from app.local_data.provenance import save_snapshot, validate_snapshot


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
    save_snapshot(scope, adapter, task, hashes, data)
    periods = {}
    for version in adapter.versions:
        periods.setdefault(SOURCE_NAMES[version["source"]], []).append(version["quarter"])
    metadata = {
        "local_snapshot": scope.snapshot_id,
        "periods": {
            key: "~".join(sorted(values)[:: max(1, len(values) - 1)])
            for key, values in periods.items()
        },
    }
    persist_input_facts(scope, data, {}, [], metadata)
    report = evaluate(data, profile_rows=profiles)
    with connect(scope.path) as db:
        map_rows = db.execute(
            "SELECT DISTINCT r.raw_row_id FROM raw_response_rows r "
            "JOIN raw_responses p USING(response_id) WHERE p.request_id=? "
            "AND p.snapshot_id=? AND p.source='map'",
            (scope.request_id, scope.snapshot_id),
        ).fetchall()
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
    connection=None,
):
    adapter = adapter if adapter is not None else validate_snapshot(scope)
    if adapter is None:
        raise ValueError("로컬 스냅샷 없음")
    if not any(v["source"] == source and v["version_id"] == version_id for v in adapter.versions):
        raise ValueError("다른 버전의 직접 셀")
    with adapter.connection() as db:
        row = db.execute(
            f"SELECT payload,columns_json,industry_code FROM {source} JOIN source_fields "
            "USING(version_id) WHERE version_id=? AND row_key=?",
            (version_id, row_key),
        ).fetchone()
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
        source=SOURCE_NAMES[source],
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
        connection=connection,
    )
