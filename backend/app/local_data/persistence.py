"""로컬 계산 자료를 기존 채점·fact 저장기에 넘깁니다."""

import json

from app.agents.agentic.registry import _config, persist_input_facts, persist_report
from app.agents.agentic.scoring import evaluate
from app.local_data.provenance import save_snapshot, validate_snapshot


def persist_local(task, scope, adapter, data=None):
    profiles, hashes, _ = _config(scope, local=True)
    data = data if data is not None else adapter.analyze(task)
    save_snapshot(scope, adapter, task, hashes, data)
    periods = {}
    from .adapter import SOURCE_NAMES

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
    score_id = persist_report(scope, report, {}, [], metadata)
    return data, report, score_id


def register_cell(scope, source, version_id, row_key, column, *, metric, unit):
    from app.agents.agentic.registry import register_fact

    from .adapter import SOURCE_NAMES

    adapter = validate_snapshot(scope)
    if adapter is None:
        raise ValueError("로컬 스냅샷 없음")
    if not any(v["source"] == source and v["version_id"] == version_id for v in adapter.versions):
        raise ValueError("다른 버전의 직접 셀")
    with adapter.connection() as db:
        row = db.execute(
            f"SELECT payload,columns_json FROM {source} JOIN source_fields "
            "USING(version_id) WHERE version_id=? AND row_key=?",
            (version_id, row_key),
        ).fetchone()
    if row is None:
        raise ValueError("원문 행 없음")
    raw = dict(zip(json.loads(row[1]), json.loads(row[0]), strict=True))
    if column not in raw or raw[column] is None:
        raise ValueError("원문 열 없음")
    return register_fact(
        scope,
        industry_code=None,
        source=SOURCE_NAMES[source],
        metric=metric,
        value=raw[column],
        unit=unit,
        status="observed",
        row_ids=[],
        comparison={"input_versions": {"local_snapshot": scope.snapshot_id}},
        local_cell={"version_id": version_id, "row_key": row_key, "column": column},
    )
