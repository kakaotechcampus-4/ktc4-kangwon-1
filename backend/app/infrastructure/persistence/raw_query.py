import json
import math
import sqlite3
from time import monotonic

from app.application.errors import RawQueryRejected
from app.domain.geo import haversine_m
from app.domain.raw_views import FIELDS, LOCAL_VIEWS, VIEWS
from app.infrastructure.persistence.connection import readonly

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


def run_query(scope, sql, params, *, max_rows, snapshot, adapter):
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
            json.dumps(params, allow_nan=False)
            if progress():
                raise RawQueryRejected("SQL_TIMEOUT", "원문 조회가 2초를 초과했습니다.")
            cursor = db.execute(sql, params)
            columns = [c[0] for c in cursor.description]
            if len(set(columns)) != len(columns):
                raise RawQueryRejected("SQL_DENIED", "중복 출력 열 이름은 허용하지 않습니다.")
            rows = cursor.fetchmany(max_rows + 1)
        except (sqlite3.Error, OverflowError, ValueError):
            raise RawQueryRejected(
                "SQL_TIMEOUT" if timed_out else "SQL_DENIED",
                "원문 조회 시간 초과" if timed_out else "허용되지 않거나 잘못된 원문 조회입니다.",
            ) from None
    return columns, rows, mappings
