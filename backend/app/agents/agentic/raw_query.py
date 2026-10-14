"""읽기 전용 SQL과 authorizer로 현재 원문 뷰만 노출합니다."""

import json
import math
import re
import sqlite3
from time import monotonic

from app.concurrency import run_in_thread
from app.db.connection import connect, readonly
from app.geo import haversine_m
from app.local_data.persistence import register_cell
from app.local_data.provenance import load_snapshot, validate_snapshot

from .contracts import QueryRawInput, RawQueryResult, RawQueryRow, ToolError, ToolReply
from .facts import register_fact

VIEWS = {
    "v_raw_stores": "commercial_area",
    "v_raw_lifecycle": "business_lifecycle",
    "v_raw_floating": "floating_population",
    "v_raw_resident": "resident_population",
    "v_raw_worker": "worker_population",
    "v_raw_map": "map",
    "v_raw_regulation": "regulation",
}
LOCAL_VIEWS = set(VIEWS) | {"v_ref_district_counts"}
FUNCTIONS = {
    "json_extract",
    "json_type",
    "count",
    "sum",
    "avg",
    "min",
    "max",
    "abs",
    "round",
    "coalesce",
    "nullif",
    "length",
    "lower",
    "upper",
    "like",
    "substr",
    "instr",
}
FIELDS = {
    "store_count": ("SIMILR_INDUTY_STOR_CO", "store_count", "개"),
    "opening_count": ("OPBIZ_STOR_CO", "opening_count", "개"),
    "closing_count": ("CLSBIZ_STOR_CO", "closing_count", "개"),
    "name": ("place_name", "place_name", "이름"),
    "kakao_category": ("category_name", "kakao_category", "분류"),
    "distance_m": ("distance", "distance_m", "m"),
}


def error(code, message):
    return ToolReply(status="error", error=ToolError(code=code, message=message))


def _authorizer(action, arg1, arg2, database, origin):
    arg1 = arg1.lower() if arg1 else arg1
    arg2 = arg2.lower() if arg2 else arg2
    origin = origin.lower() if origin else origin
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        # UNION 뷰의 COUNT(*)는 SQLite가 DB 이름 없는 빈 열 읽기로 추가 검사합니다.
        if database is None and origin is None and arg2 == "" and arg1 in LOCAL_VIEWS:
            return sqlite3.SQLITE_OK
        allowed = (
            (database == "temp" and arg1 in LOCAL_VIEWS)
            or (
                database == "local"
                and origin in LOCAL_VIEWS
                and arg1
                in {"stores", "lifecycle", "floating", "resident", "worker", "district_counts"}
            )
            or database == "main"
            and (
                arg1 in VIEWS
                or (arg1 in {"raw_rows", "raw_response_rows", "raw_responses"} and origin in VIEWS)
            )
        )
        return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION:
        allowed = arg2 in FUNCTIONS or (
            arg2 in {"raw_request_id", "raw_snapshot_id", "scope_distance", "json_object"}
            and origin in VIEWS
        )
        return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_DENY


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


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def local_views(db, scope, snapshot, adapter):
    spatial = json.loads(snapshot["scope_json"])
    db.execute("ATTACH DATABASE ? AS local", (adapter.path.as_uri() + "?mode=ro",))
    db.create_function(
        "scope_distance",
        2,
        lambda lat, lon: (
            haversine_m(spatial["latitude"], spatial["longitude"], lat, lon)
            if lat is not None and lon is not None
            else float("inf")
        ),
    )
    mappings = {}
    for source in ("stores", "lifecycle", "floating", "resident", "worker"):
        view = "v_raw_" + source
        parts = []
        for version in adapter.versions:
            if version["source"] != source:
                continue
            vid = version["version_id"]
            fields = json.loads(
                db.execute(
                    "SELECT columns_json FROM local.source_fields WHERE version_id=?", (vid,)
                ).fetchone()[0]
            )
            aliases = {
                "quarter": "STDR_YYQU_CD",
                "trade_area_code": "TRDAR_CD",
                "seoul_industry_code": "SVC_INDUTY_CD",
                **{alias: spec[0] for alias, spec in FIELDS.items()},
            }
            if source == "stores":
                aliases.update(
                    store_id="상가업소번호",
                    middle_code="상권업종중분류코드",
                    small_code="상권업종소분류코드",
                )
            selected = [
                "version_id",
                "row_key AS raw_row_id",
                "industry_code",
                "latitude",
                "longitude",
                quote(scope.request_id) + " AS request_id",
                quote(scope.snapshot_id) + " AS snapshot_id",
            ]
            mapping = {}
            for index, field in enumerate(fields):
                for alias in [
                    field,
                    *[a for a, original in aliases.items() if original == field and a != field],
                ]:
                    if alias.lower() in {
                        "version_id",
                        "raw_row_id",
                        "industry_code",
                        "latitude",
                        "longitude",
                        "request_id",
                        "snapshot_id",
                    }:
                        continue
                    selected.append(
                        f"json_extract(payload,'$[{index}]') AS "
                        + '"'
                        + alias.replace('"', '""')
                        + '"'
                    )
                    mapping[alias.lower()] = field
            obj = ",".join(
                f"{quote(field)},json_extract(payload,'$[{i}]')" for i, field in enumerate(fields)
            )
            selected.append(f"json_object({obj}) AS raw_json")
            condition = "version_id=" + quote(vid)
            if source == "stores":
                dy = spatial["radius_m"] / 110000
                dx = dy / math.cos(math.radians(spatial["latitude"]))
                condition += (
                    f" AND latitude BETWEEN {spatial['latitude'] - dy}"
                    f" AND {spatial['latitude'] + dy}"
                    f" AND longitude BETWEEN {spatial['longitude'] - dx}"
                    f" AND {spatial['longitude'] + dx}"
                    f" AND scope_distance(latitude,longitude)<={float(spatial['radius_m'])}"
                )
            else:
                codes = (
                    [spatial.get("area_selection", {}).get("area_code")]
                    if source == "lifecycle"
                    else spatial.get("selected_trade_area_codes", [])
                )
                codes = [c for c in codes if c]
                condition += (
                    " AND area_code IN (" + (",".join(quote(c) for c in codes) or "NULL") + ")"
                )
            parts.append(f"SELECT {','.join(selected)} FROM local.{source} WHERE {condition}")
            mappings.setdefault(view, (source, {}))[1][vid] = mapping
        if parts:
            db.execute(f"CREATE TEMP VIEW {view} AS " + " UNION ALL ".join(parts))
    versions = [quote(v["version_id"]) for v in adapter.versions if v["source"] == "stores"]
    db.execute(
        "CREATE TEMP VIEW v_ref_district_counts AS "
        "SELECT version_id,district_code,industry_code,count "
        "FROM local.district_counts WHERE version_id IN ("
        + (",".join(versions) or "NULL")
        + ") AND district_code="
        + quote(spatial.get("district_code", ""))
    )
    return mappings


def _query(scope, input):
    sql = input.sql.strip().removesuffix(";").strip()
    if not re.match(r"^SELECT\b", sql, re.I) or re.search(r";|--|/\*|\bWITH\b", sql, re.I):
        return error("SQL_DENIED", "승인된 뷰의 단일 SELECT만 허용합니다.")
    view, projection = _projection(sql)
    snapshot = load_snapshot(scope)
    adapter = validate_snapshot(scope) if snapshot else None
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
        and "__server_lineage__" not in projection
    ):
        hidden = raw_alias = "__server_lineage__"
        sql = re.sub(
            r"\bFROM\b", ", raw_row_id AS __server_lineage__ FROM", sql, count=1, flags=re.I
        )
    if is_local:
        sql = re.sub(
            r"\bFROM\b", ", version_id AS __server_version__ FROM", sql, count=1, flags=re.I
        )
    deadline = monotonic() + 2
    timed_out = False

    def progress():
        nonlocal timed_out
        timed_out = monotonic() > deadline
        return int(timed_out)

    with readonly(scope.path, timeout=2) as db:
        mappings = local_views(db, scope, snapshot, adapter) if snapshot else {}
        db.execute("PRAGMA query_only=ON")
        db.create_function("raw_request_id", 0, lambda: scope.request_id)
        db.create_function("raw_snapshot_id", 0, lambda: scope.snapshot_id)

        def authorize(action, arg1, arg2, database, origin):
            if (
                snapshot
                and action == sqlite3.SQLITE_READ
                and database == "main"
                and ((arg1 or "").lower() in mappings or (origin or "").lower() in mappings)
            ):
                return sqlite3.SQLITE_DENY
            return _authorizer(action, arg1, arg2, database, origin)

        db.set_authorizer(authorize)
        db.set_progress_handler(progress, 100)
        try:
            json.dumps(input.params, allow_nan=False)
            if progress():
                return error("SQL_TIMEOUT", "원문 조회가 2초를 초과했습니다.")
            cursor = db.execute(sql, input.params)
            columns = [c[0] for c in cursor.description]
            if len(set(columns)) != len(columns):
                return error("SQL_DENIED", "중복 출력 열 이름은 허용하지 않습니다.")
            rows = cursor.fetchmany(input.max_rows + 1)
        except (sqlite3.Error, OverflowError, ValueError):
            return error(
                "SQL_TIMEOUT" if timed_out else "SQL_DENIED",
                "원문 조회 시간 초과" if timed_out else "허용되지 않거나 잘못된 원문 조회입니다.",
            )
    public_columns = [c for c in columns if c not in (hidden, "__server_version__")]
    citable = set()
    output = []
    truncated = len(rows) > input.max_rows
    output_bytes = len(json.dumps(public_columns, ensure_ascii=False).encode()) + 1024
    with connect(scope.path) as db:
        for values in rows[: input.max_rows]:
            value_map = dict(zip(columns, values, strict=True))
            ref = value_map.get(raw_alias) if raw_alias else None
            if hidden:
                value_map.pop(hidden, None)
            version = value_map.pop("__server_version__", None)
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
                            connection=db,
                        )
                        facts.append(fact)
                        citable.add(output_alias)
                output.append(RawQueryRow(raw_row_refs=[ref], values=value_map, fact_ids=facts))
                continue
            original = (
                db.execute(
                    "SELECT r.raw_json,p.source FROM raw_rows r "
                    "JOIN raw_response_rows e USING(raw_row_id) "
                    "JOIN raw_responses p USING(response_id) "
                    "WHERE r.raw_row_id=? AND p.request_id=? AND p.snapshot_id=?",
                    (ref, scope.request_id, scope.snapshot_id),
                ).fetchone()
                if ref
                else None
            )
            facts = []
            if original and view and original[1] == VIEWS[view]:
                raw = json.loads(original[0])
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
                        connection=db,
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
