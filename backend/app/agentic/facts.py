"""원문 계보를 가진 불변 fact 저장입니다. SQLite는 호출자가 스레드로 격리합니다."""

import asyncio
import uuid
from contextlib import nullcontext

from app.canonical import canonical_hash, canonical_json
from app.clock import utc_now_iso
from app.db.connection import connect
from app.local_data.provenance import pin_provenance

CALC_VERSION = "rubric-v0.8-pr3-1"


def register_fact(
    scope,
    *,
    industry_code,
    source,
    metric,
    value,
    unit,
    status,
    row_ids,
    comparison=None,
    period="기준선별 시점",
    response_ids=(),
    field_pointer="/",
    connection=None,
    local_cell=None,
    parent_fact_ids=(),
    retain_unknown_value=False,
):
    """동일 값·계보는 기존 ID를 반환합니다. 값을 바꾸면 새 ID를 생성합니다."""
    local = comparison and comparison.get("input_versions", {}).get("local_snapshot")
    if local and local != scope.snapshot_id:
        raise ValueError("다른 로컬 스냅샷")
    if local:
        comparison = {"input_versions": {"local_snapshot": local}}
    row_ids = sorted(set(row_ids))
    comparison = comparison or {}
    if retain_unknown_value and metric != "space_fit":
        raise ValueError("미확인 객체 값은 공간 비교에만 보존할 수 있습니다.")
    parent_fact_ids = sorted(set(parent_fact_ids))
    if status != "observed" and not (status == "unknown" and retain_unknown_value):
        value = None
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
    identity_hash = canonical_hash(identity)
    with connect(scope.path) if connection is None else nullcontext(connection) as db:
        if not db.in_transaction:
            db.execute("BEGIN IMMEDIATE")
        for offset in range(0, len(row_ids), 400):
            if scope.cancelled.is_set():
                raise asyncio.CancelledError()
            batch = row_ids[offset : offset + 400]
            found = {
                r[0]
                for r in db.execute(
                    "SELECT DISTINCT e.raw_row_id FROM raw_response_rows e "
                    "INDEXED BY raw_response_row_ref CROSS JOIN raw_responses p "
                    "ON p.response_id=e.response_id WHERE e.raw_row_id IN ("
                    + ",".join("?" for _ in batch)
                    + ") AND p.request_id=? AND p.snapshot_id=?",
                    [*batch, scope.request_id, scope.snapshot_id],
                )
            }
            if set(batch) != found:
                raise ValueError("다른 요청·스냅샷의 원문을 fact 근거로 사용할 수 없습니다.")
        for response in response_ids:
            if (
                db.execute(
                    "SELECT 1 FROM raw_responses WHERE response_id=? AND request_id=? AND "
                    "snapshot_id=?",
                    (response, scope.request_id, scope.snapshot_id),
                ).fetchone()
                is None
            ):
                raise ValueError("응답 계보의 요청 범위가 다릅니다.")
        for parent_id in parent_fact_ids:
            if scope.cancelled.is_set():
                raise asyncio.CancelledError()
            parent = db.execute(
                "SELECT industry_code,status,citable FROM facts WHERE fact_id=? "
                "AND request_id=? AND snapshot_id=?",
                (parent_id, scope.request_id, scope.snapshot_id),
            ).fetchone()
            if parent is None or parent[0] not in (None, industry_code):
                raise ValueError("부모 fact의 요청·스냅샷·업종이 다릅니다.")
            if status == "observed" and (parent[1] != "observed" or not parent[2]):
                raise ValueError("관측 비교에는 인용 가능한 부모 fact가 필요합니다.")
        citable = status == "observed" and bool(row_ids or response_ids or local or parent_fact_ids)
        if status == "observed" and not citable:
            raise ValueError("관측 fact에는 검증 가능한 원문 계보가 필요합니다.")
        old = db.execute(
            "SELECT fact_id FROM facts WHERE snapshot_id=? AND identity_hash=?",
            (scope.snapshot_id, identity_hash),
        ).fetchone()
        if old:
            return old[0]
        fact_id = "f_" + str(uuid.uuid4())
        db.execute(
            "INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                fact_id,
                scope.request_id,
                scope.snapshot_id,
                industry_code,
                source,
                metric,
                canonical_json(value),
                unit,
                period,
                canonical_json(
                    {"snapshot_id": scope.snapshot_id}
                    | (
                        {}
                        if local
                        else comparison.get("input_versions", {}).get("spatial_scope", {})
                    )
                ),
                canonical_json(
                    comparison
                    | {"response_ids": list(response_ids)}
                    | ({"parent_fact_ids": parent_fact_ids} if parent_fact_ids else {})
                ),
                status,
                int(citable),
                CALC_VERSION,
                canonical_hash({"rows": row_ids, "parents": parent_fact_ids})
                if parent_fact_ids
                else canonical_hash(row_ids),
                identity_hash,
                utc_now_iso(),
            ),
        )
        if local:
            ref = pin_provenance(db, scope, source, metric, industry_code, CALC_VERSION, local_cell)
            db.execute(
                "INSERT INTO local_fact_lineage VALUES(?,?,?,?)",
                (
                    fact_id,
                    ref,
                    local_cell["row_key"] if local_cell else None,
                    local_cell["column"] if local_cell else None,
                ),
            )
        for offset in range(0, len(row_ids), 400):
            if scope.cancelled.is_set():
                raise asyncio.CancelledError()
            db.executemany(
                "INSERT INTO fact_sources VALUES(?,?,?)",
                [(fact_id, row, field_pointer) for row in row_ids[offset : offset + 400]],
            )
        if parent_fact_ids:
            db.executemany(
                "INSERT INTO fact_parents VALUES(?,?)",
                [(fact_id, parent_id) for parent_id in parent_fact_ids],
            )
    return fact_id
