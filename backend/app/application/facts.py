"""원문 계보를 가진 불변 fact 저장입니다. SQLite는 호출자가 스레드로 격리합니다."""

import asyncio
import uuid
from contextlib import nullcontext

from app.application.ports.storage import open_stores
from app.domain.facts import CALC_VERSION, fact_identity, is_citable
from app.shared.canonical import canonical_hash, canonical_json
from app.shared.clock import utc_now_iso


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
    stores=None,
    local_cell=None,
    parent_fact_ids=(),
    retain_unknown_value=False,
):
    """동일 값·계보는 기존 ID를 반환합니다. 값을 바꾸면 새 ID를 생성합니다."""
    if status == "observed" and value is None:
        raise ValueError("관측 fact에는 실제 값이 필요합니다.")
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
    identity_hash = canonical_hash(
        fact_identity(
            industry_code=industry_code,
            source=source,
            metric=metric,
            value=value,
            unit=unit,
            status=status,
            period=period,
            row_ids=row_ids,
            response_ids=response_ids,
            comparison=comparison,
            local_cell=local_cell,
            parent_fact_ids=parent_fact_ids,
        )
    )
    with open_stores(scope.path) if stores is None else nullcontext(stores) as st:
        st.begin_immediate()
        for offset in range(0, len(row_ids), 400):
            if scope.cancelled.is_set():
                raise asyncio.CancelledError()
            batch = row_ids[offset : offset + 400]
            found = st.raw.raw_rows_in_scope(batch, scope.request_id, scope.snapshot_id)
            if set(batch) != found:
                raise ValueError("다른 요청·스냅샷의 원문을 fact 근거로 사용할 수 없습니다.")
        for response in response_ids:
            if not st.raw.response_in_scope(response, scope.request_id, scope.snapshot_id):
                raise ValueError("응답 계보의 요청 범위가 다릅니다.")
        for parent_id in parent_fact_ids:
            if scope.cancelled.is_set():
                raise asyncio.CancelledError()
            parent = st.facts.fact_scope_row(parent_id, scope.request_id, scope.snapshot_id)
            if parent is None or parent[0] not in (None, industry_code):
                raise ValueError("부모 fact의 요청·스냅샷·업종이 다릅니다.")
            if status == "observed" and (parent[1] != "observed" or not parent[2]):
                raise ValueError("관측 비교에는 인용 가능한 부모 fact가 필요합니다.")
        citable = is_citable(
            status,
            row_ids=row_ids,
            response_ids=response_ids,
            local=local,
            parent_fact_ids=parent_fact_ids,
        )
        if status == "observed" and not citable:
            raise ValueError("관측 fact에는 검증 가능한 원문 계보가 필요합니다.")
        old = st.facts.fact_id_by_identity(scope.snapshot_id, identity_hash)
        if old:
            return old
        fact_id = "f_" + str(uuid.uuid4())
        st.facts.insert_fact(
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
            ref = st.pin_provenance(
                scope, source, metric, industry_code, CALC_VERSION, local_cell, unit
            )
            st.facts.insert_local_fact_lineage(
                fact_id,
                ref,
                local_cell["row_key"] if local_cell else None,
                local_cell["column"] if local_cell else None,
            )
        for offset in range(0, len(row_ids), 400):
            if scope.cancelled.is_set():
                raise asyncio.CancelledError()
            st.facts.insert_fact_sources(
                [(fact_id, row, field_pointer) for row in row_ids[offset : offset + 400]]
            )
        if parent_fact_ids:
            st.facts.insert_fact_parents([(fact_id, parent_id) for parent_id in parent_fact_ids])
    return fact_id
