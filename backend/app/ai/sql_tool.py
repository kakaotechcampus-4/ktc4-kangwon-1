"""읽기 전용 SQL과 authorizer로 현재 원문 뷰만 노출합니다."""

import json
import re

from app.application.errors import RawQueryRejected
from app.application.facts import register_fact
from app.application.local_snapshot import register_cell
from app.application.ports.storage import open_stores, storage
from app.domain.contracts import QueryRawInput, RawQueryResult, RawQueryRow, ToolReply, error
from app.domain.raw_views import FIELDS, LINEAGE_COLUMN, LOCAL_VIEWS, VERSION_COLUMN, VIEWS
from app.shared.concurrency import run_in_thread


def _projection(sql):
    # shortcut: 1차는 단일 뷰의 명시적 열만 인용합니다. AST 도입 때 복합 조회 계보를 확장합니다.
    if (
        re.search(r"\b(?:UNION|INTERSECT|EXCEPT|JOIN)\b", sql, re.I)
        or len(re.findall(r"\bSELECT\b", sql, re.I)) != 1
    ):
        return None, {}
    match = re.fullmatch(
        r"\s*SELECT\s+([\w\s,]+)\s+FROM\s+(v_(?:raw|ref)_\w+)(?:\s+(?:WHERE|ORDER\s+BY|LIMIT)\s+.*)?",
        sql,
        re.I | re.S,
    )
    if not match or match[2].lower() not in LOCAL_VIEWS:
        return None, {}
    columns = {}
    for part in match[1].split(","):
        field = re.fullmatch(r"\s*(\w+)(?:\s+AS\s+(\w+))?\s*", part, re.I)
        if not field:
            return None, {}
        columns[(field[2] or field[1]).lower()] = field[1].lower()
    if len(columns) != len(match[1].split(",")):
        return None, {}
    return match[2].lower(), columns


def _query(scope, input):
    sql = input.sql.strip().removesuffix(";").strip()
    if not re.match(r"^SELECT\b", sql, re.I) or re.search(r";|--|/\*|\bWITH\b", sql, re.I):
        return error("SQL_DENIED", "승인된 뷰의 단일 SELECT만 허용합니다.")
    view, projection = _projection(sql)
    snapshot = storage().provenance.load_snapshot(scope)
    adapter = storage().provenance.validate_snapshot(scope) if snapshot else None
    is_local = snapshot is not None and view in {
        "v_raw_stores",
        "v_raw_lifecycle",
        "v_raw_floating",
        "v_raw_resident",
        "v_raw_worker",
    }
    raw_alias = next((key for key, field in projection.items() if field == "raw_row_id"), None)
    hidden = None
    if (
        view
        and view != "v_ref_district_counts"
        and raw_alias is None
        and LINEAGE_COLUMN not in projection
    ):
        hidden = raw_alias = LINEAGE_COLUMN
    try:
        columns, rows, mappings = storage().raw_query(
            scope,
            sql,
            input.params,
            max_rows=input.max_rows,
            snapshot=snapshot,
            adapter=adapter,
            lineage=hidden is not None,
            version=is_local,
        )
    except RawQueryRejected as exc:
        return error(exc.code, exc.message)
    public_columns = [c for c in columns if c not in (hidden, VERSION_COLUMN)]
    citable = set()
    output = []
    truncated = len(rows) > input.max_rows
    output_bytes = len(json.dumps(public_columns, ensure_ascii=False).encode()) + 1024
    with open_stores(scope) as st:
        for values in rows[: input.max_rows]:
            value_map = dict(zip(columns, values, strict=True))
            ref = value_map.get(raw_alias) if raw_alias else None
            if hidden:
                value_map.pop(hidden, None)
            version = value_map.pop(VERSION_COLUMN, None)
            row_bytes = len(json.dumps(value_map, ensure_ascii=False).encode())
            # 계보와 응답 메타데이터 몫도 남겨 모델·감사 기록을 같은 상한에 가둡니다.
            if output_bytes + row_bytes + 200 > 65536:
                truncated = True
                break
            output_bytes += row_bytes + 200
            if is_local and version and ref:
                source, version_mappings = mappings[view]
                mapping = version_mappings[version]
                facts = []
                for alias, field in projection.items():
                    original_column = mapping.get(field)
                    output_alias = next((c for c in value_map if c.lower() == alias), alias)
                    if original_column and value_map.get(output_alias) is not None:
                        metric, unit = (
                            FIELDS[field][1:] if field in FIELDS else ("raw_cell", "원문")
                        )
                        fact = register_cell(
                            scope,
                            source,
                            version,
                            ref,
                            original_column,
                            metric=metric,
                            unit=unit,
                            expected_value=value_map[output_alias],
                            adapter=adapter,
                            stores=st,
                        )
                        facts.append(fact)
                        citable.add(output_alias)
                output.append(RawQueryRow(raw_row_refs=[ref], values=value_map, fact_ids=facts))
                continue
            original = (
                st.raw.raw_row_with_source(ref, scope.request_id, scope.snapshot_id)
                if ref
                else None
            )
            facts = []
            if original and view and original.source == VIEWS[view]:
                raw = original.value
                for alias, field in projection.items():
                    if field not in FIELDS or alias not in value_map:
                        continue
                    key, metric, unit = FIELDS[field]
                    value = raw.get(key)
                    if value is None or value != value_map[alias]:
                        continue
                    fact = register_fact(
                        scope,
                        industry_code=None,
                        source=VIEWS[view],
                        metric=metric,
                        value=value,
                        unit=unit,
                        status="observed",
                        row_ids=[ref],
                        field_pointer="/" + key,
                        period=str(raw.get("STDR_YYQU_CD") or "조회 시점"),
                        stores=st,
                    )
                    facts.append(fact)
                    citable.add(alias)
            output.append(
                RawQueryRow(
                    raw_row_refs=[ref] if original else [], values=value_map, fact_ids=facts
                )
            )
    reply = ToolReply(
        status="partial" if truncated else "ok",
        truncated=truncated,
        data=RawQueryResult(
            columns=public_columns,
            rows=output,
            uncitable_columns=[c for c in public_columns if c not in citable],
        ),
        fact_ids=[f for row in output for f in row.fact_ids],
    )
    while len(reply.model_dump_json().encode()) > 65536 and reply.data.rows:
        reply.data.rows.pop()
        reply.fact_ids = [f for row in reply.data.rows for f in row.fact_ids]
        reply.status, reply.truncated = "partial", True
    if len(reply.model_dump_json().encode()) > 65536:
        return error("SQL_DENIED", "원문 조회 열 정보가 응답 크기 상한을 초과했습니다.")
    return reply


async def query_raw(scope, sql, params=None, max_rows=50):
    input = QueryRawInput(sql=sql, params=params or {}, max_rows=max_rows)
    return await run_in_thread(_query, scope, input)
