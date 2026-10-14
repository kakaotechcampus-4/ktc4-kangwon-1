"""읽기 전용 SQL과 authorizer로 현재 원문 뷰만 노출합니다."""

import json
import re
import sqlite3
from contextlib import closing
from time import monotonic

from app.db.connection import connect
from app.storage.raw import _write

from .contracts import QueryRawInput, RawQueryResult, RawQueryRow, ToolError, ToolReply
from .registry import register_fact

VIEWS = {
    "v_raw_stores": "commercial_area",
    "v_raw_lifecycle": "business_lifecycle",
    "v_raw_floating": "floating_population",
    "v_raw_resident": "resident_population",
    "v_raw_worker": "worker_population",
    "v_raw_map": "map",
    "v_raw_regulation": "regulation",
}
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
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        allowed = database == "main" and (
            arg1 in VIEWS
            or (arg1 in {"raw_rows", "raw_response_rows", "raw_responses"} and origin in VIEWS)
        )
        return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION:
        allowed = arg2 in FUNCTIONS or (
            arg2 in {"raw_request_id", "raw_snapshot_id"} and origin in VIEWS
        )
        return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_DENY


def _projection(sql):
    # shortcut: 1차는 단일 뷰의 명시적 열만 인용합니다. AST 도입 때 복합 조회 계보를 확장합니다.
    match = re.fullmatch(
        r"\s*SELECT\s+([\w\s,]+)\s+FROM\s+(v_raw_\w+)(?:\s+(?:WHERE|ORDER\s+BY|LIMIT)\s+.*)?",
        sql,
        re.I | re.S,
    )
    if not match or match[2].lower() not in VIEWS:
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
    raw_alias = next((key for key, field in projection.items() if field == "raw_row_id"), None)
    hidden = None
    if view and raw_alias is None and "__server_lineage__" not in projection:
        hidden = raw_alias = "__server_lineage__"
        sql = re.sub(
            r"\bFROM\b", ", raw_row_id AS __server_lineage__ FROM", sql, count=1, flags=re.I
        )
    deadline = monotonic() + 2
    timed_out = False

    def progress():
        nonlocal timed_out
        timed_out = monotonic() > deadline
        return int(timed_out)

    with closing(
        sqlite3.connect(scope.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    ) as db:
        db.execute("PRAGMA query_only=ON")
        db.create_function("raw_request_id", 0, lambda: scope.request_id)
        db.create_function("raw_snapshot_id", 0, lambda: scope.snapshot_id)
        db.set_authorizer(_authorizer)
        db.set_progress_handler(progress, 100)
        try:
            if progress():
                return error("SQL_TIMEOUT", "원문 조회가 2초를 초과했습니다.")
            cursor = db.execute(sql, input.params)
            columns = [c[0] for c in cursor.description]
            if len(set(columns)) != len(columns):
                return error("SQL_DENIED", "중복 출력 열 이름은 허용하지 않습니다.")
            rows = cursor.fetchmany(input.max_rows + 1)
        except sqlite3.Error:
            return error(
                "SQL_TIMEOUT" if timed_out else "SQL_DENIED",
                "원문 조회 시간 초과" if timed_out else "허용되지 않거나 잘못된 원문 조회입니다.",
            )
    public_columns = [c for c in columns if c != hidden]
    citable = set()
    output = []
    with connect(scope.path) as db:
        for values in rows[: input.max_rows]:
            value_map = dict(zip(columns, values, strict=True))
            ref = value_map.get(raw_alias) if raw_alias else None
            if hidden:
                value_map.pop(hidden, None)
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
    truncated = len(rows) > input.max_rows
    return ToolReply(
        status="partial" if truncated else "ok",
        truncated=truncated,
        data=RawQueryResult(
            columns=public_columns,
            rows=output,
            uncitable_columns=[c for c in public_columns if c not in citable],
        ),
        fact_ids=[f for row in output for f in row.fact_ids],
    )


async def query_raw(scope, sql, params=None, max_rows=50):
    input = QueryRawInput(sql=sql, params=params or {}, max_rows=max_rows)
    return await _write(_query, scope, input)
