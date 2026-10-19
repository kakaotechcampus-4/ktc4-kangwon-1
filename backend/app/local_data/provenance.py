"""요청별 자료 버전과 셀/집계 계보를 작은 참조로 저장합니다."""

import json
from pathlib import Path

from app.agentic.c1_units import NEARBY_UNIT
from app.canonical import canonical_hash, canonical_json
from app.db.connection import connect
from app.local_data.adapter import SOURCE_NAMES, LocalAdapter


def save_snapshot(scope, adapter, task, config_hashes=None, data=None):
    spatial = {
        "latitude": task.site.latitude,
        "longitude": task.site.longitude,
        "radius_m": task.radius_m,
    }
    if data:
        spatial.update(
            selected_trade_area_codes=data.get("selected_trade_area_codes", []),
            area_selection=data.get("area_selection"),
            district_code=data.get("district_code"),
            comparison_radius_m=data.get("comparison_radius_m"),
        )
    with connect(scope.path) as db:
        db.execute(
            "INSERT INTO local_snapshots VALUES(?,?,?,?,?)",
            (
                scope.snapshot_id,
                str(adapter.path),
                canonical_json(adapter.versions),
                canonical_json(config_hashes or {}),
                canonical_json(spatial),
            ),
        )


def load_snapshot(scope):
    with connect(scope.path) as db:
        row = db.execute(
            "SELECT * FROM local_snapshots WHERE snapshot_id=?", (scope.snapshot_id,)
        ).fetchone()
        return dict(row) if row else None


def pin_provenance(db, scope, source, metric, industry, calc_version, cell=None, unit=None):
    row = db.execute(
        "SELECT versions_json,scope_json FROM local_snapshots WHERE snapshot_id=?",
        (scope.snapshot_id,),
    ).fetchone()
    if row is None:
        raise ValueError("고정된 로컬 자료 묶음이 없습니다.")
    versions = json.loads(row[0])
    refs = [v["version_id"] for v in versions if SOURCE_NAMES[v["source"]] == source]
    if metric == "competition_index" and unit == NEARBY_UNIT:
        refs += [v["version_id"] for v in versions if v["source"] == "floating"]
    # 프로필/기준값과 오프라인 시험 관측도 snapshot에 명시한 해시/조건으로 구분합니다.
    query = {"scope_ref": scope.snapshot_id, "recipe": "기존 formatter"}
    # 지표·업종 조건은 facts.metric/industry_code에 이미 있으므로 계보 연결 시 결합합니다.
    if cell:
        if cell["version_id"] not in refs:
            raise ValueError("다른 버전의 셀")
        query["version_id"] = cell["version_id"]
    identity = canonical_hash([scope.snapshot_id, source, refs, query, calc_version])
    db.execute(
        "INSERT OR IGNORE INTO local_provenance VALUES(?,?,?,?,?,?)",
        (
            identity,
            scope.snapshot_id,
            source,
            canonical_json(refs),
            canonical_json(query),
            calc_version,
        ),
    )
    return identity


def validate_snapshot(scope):
    row = load_snapshot(scope)
    if row is not None:
        return LocalAdapter(Path(row["database_path"]), json.loads(row["versions_json"]))
    return None


def expand_spatial_scope(scope, records):
    """저장은 공유 참조로 유지하고 도구·자문·보고서의 읽기 경계에서만 펼칩니다."""
    snapshot = load_snapshot(scope)
    if snapshot is None:
        return
    spatial = json.loads(snapshot["scope_json"])
    for row in records:
        if row.get("local_lineage"):
            row["spatial_scope_json"] = canonical_json(spatial | {"snapshot_id": scope.snapshot_id})
