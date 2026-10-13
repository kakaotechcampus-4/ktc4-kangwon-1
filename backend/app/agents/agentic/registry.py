"""원문 계보를 가진 불변 fact·코드 점수 저장입니다. SQLite는 호출자가 스레드로 격리합니다."""

import csv
import hashlib
import io
import json
import os
import uuid
from contextlib import nullcontext
from pathlib import Path

from app.agents.business_lifecycle import baseline as lifecycle_baseline
from app.agents.commercial_area import baseline as density_baseline
from app.agents.floating_population import baseline as population_baseline
from app.db.connection import connect
from app.industries import DATA_DIR
from app.industries.catalog import INDUSTRIES
from app.storage.raw import RawStorageError, _hash, _json, _now, _write, current_capture

from .formatter import format_snapshot
from .scoring import WEIGHTS, evaluate

CALC_VERSION = "rubric-v0.8-pr3-1"
METRICS = {
    "D1": ("pattern_fit_index", "배수", "floating_population"),
    "D2": ("day_fit_index", "배수", "floating_population"),
    "D3": ("target_age_index", "배수", "floating_population"),
    "D4": ("yoy_change", "비율", "floating_population"),
    "C1": ("competition_index", "배수", "commercial_area"),
    "C4": ("distance_m", "m", "map"),
    "S1": ("close_rate_ratio", "배수", "business_lifecycle"),
    "S2": ("net_change_index", "배수", "business_lifecycle"),
    "S3": ("turnover_ratio", "배수", "business_lifecycle"),
    "S4": ("close_trend_ratio", "배수", "business_lifecycle"),
}


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
):
    """동일 값·계보는 기존 ID를 반환합니다. 값을 바꾸면 새 ID를 생성합니다."""
    row_ids = sorted(set(row_ids))
    comparison = comparison or {}
    if status != "observed":
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
    }
    identity_hash = _hash(identity)
    with connect(scope.path) if connection is None else nullcontext(connection) as db:
        if not db.in_transaction:
            db.execute("BEGIN IMMEDIATE")
        for row_id in row_ids:
            exists = db.execute(
                "SELECT 1 FROM raw_rows r JOIN raw_responses p USING(response_id) WHERE "
                "r.raw_row_id=? AND p.request_id=? AND p.snapshot_id=?",
                (row_id, scope.request_id, scope.snapshot_id),
            ).fetchone()
            if exists is None:
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
        citable = status == "observed" and bool(row_ids or response_ids)
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
                _json(value),
                unit,
                period,
                _json(
                    {"snapshot_id": scope.snapshot_id}
                    | comparison.get("input_versions", {}).get("spatial_scope", {})
                ),
                _json(comparison | {"response_ids": list(response_ids)}),
                status,
                int(citable),
                CALC_VERSION,
                _hash(row_ids),
                identity_hash,
                _now(),
            ),
        )
        db.executemany(
            "INSERT INTO fact_sources VALUES(?,?,?)",
            [(fact_id, row, field_pointer) for row in row_ids],
        )
    return fact_id


def _config(scope):
    profile_path = DATA_DIR / "industry_profile.csv"
    profile_bytes = profile_path.read_bytes()
    profiles = list(csv.DictReader(io.StringIO(profile_bytes.decode("utf-8-sig"))))
    if (
        len(profiles) != len(INDUSTRIES)
        or {r["industry_code"] for r in profiles} != set(INDUSTRIES)
        or any(r["reviewed_v2"] != "true" for r in profiles)
    ):
        raise ValueError("승인된 51개 업종 프로필이 필요합니다.")
    configs = [
        (profile_path, profiles),
        (
            Path(population_baseline.__file__),
            [
                {
                    "configuration": "population_baseline",
                    "values": {
                        name: getattr(population_baseline, name)
                        for name in (
                            "AGE_SHARE_AVG",
                            "TIME_PER_HOUR_SHARE_AVG",
                            "WEEKEND_TO_WEEKDAY_AVG",
                            "TIME_BAND_DAILY_PERCENTILES",
                            "PATTERN_DAILY_PERCENTILES",
                            "DAILY_TOTAL_PERCENTILES",
                        )
                    },
                }
            ],
        ),
        (
            Path(density_baseline.__file__),
            [
                {
                    "configuration": "density_baseline",
                    "values": density_baseline.SEOUL_INDUSTRY_DENSITY_PERCENTILES,
                }
            ],
        ),
        (
            Path(lifecycle_baseline.__file__),
            [
                {
                    "configuration": "lifecycle_baseline",
                    "values": lifecycle_baseline.SEOUL_INDUSTRY_LIFECYCLE_BASELINE,
                }
            ],
        ),
    ]
    hashes = {}
    for path, rows in configs:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[path.name + str(path.parent.name)] = digest
        with connect(scope.path) as db:
            old = db.execute(
                "SELECT response_id FROM raw_responses WHERE snapshot_id=? AND "
                "source='baseline' AND json_extract(request_args_json,'$.file_hash')=?",
                (scope.snapshot_id, digest),
            ).fetchone()
        if not old:
            scope.record_sync(
                source="baseline",
                source_type="file",
                args={"file_name": path.name, "file_hash": digest, "quarter": "20262"},
                page="file",
                status=None,
                payload={"rows": rows},
            )
    with connect(scope.path) as db:
        profile_refs = {}
        shared = []
        for row in db.execute(
            "SELECT r.raw_row_id,r.raw_json FROM raw_rows r JOIN raw_responses p "
            "USING(response_id) WHERE p.snapshot_id=? AND p.source='baseline' AND "
            "r.duplicate_of IS NULL",
            (scope.snapshot_id,),
        ):
            value = json.loads(row[1])
            if value.get("industry_code"):
                profile_refs[value["industry_code"]] = row[0]
            else:
                shared.append(row[0])
    return {r["industry_code"]: r for r in profiles}, hashes, (shared, profile_refs)


def persist_report(scope, report, lineage, responses, version=None):
    """점수 숫자는 순수 엔진에서만 계산합니다. L은 unknown·판단 미검토로 저장합니다."""
    score_id = "sc_" + str(uuid.uuid4())
    facts_by_item = {}
    response_refs = {}
    for response in responses:
        response_refs.setdefault(response["source"], []).append(response["response_id"])
    with connect(scope.path) as db:
        for row in report["rows"]:
            for item, score in row["items"].items():
                if item == "L":
                    facts_by_item[(row["code"], item)] = []
                    continue
                metric, unit, source = METRICS[item]
                value = score["value"]
                if item == "D1" and isinstance(value, (int, float)):
                    metric, unit = "mean_daily_per_trade_area", "명/일"
                if item == "D3" and isinstance(value, dict):
                    source = {"상주": "resident_population", "직장": "worker_population"}.get(
                        value.get("population"), source
                    )
                refs = (
                    list(
                        lineage.get("industry_rows", {})
                        .get(source, {})
                        .get(row["code"], lineage.get(source, []))
                    )
                    if score["status"] == "observed"
                    else []
                ) + list(lineage.get("baseline", []))
                if row["code"] in lineage.get("profiles", {}):
                    refs.append(lineage["profiles"][row["code"]])
                if item == "C1" and score["status"] == "observed":
                    refs.extend(lineage.get("floating_population", []))
                response_ids = response_refs.get(source, [])
                if score["status"] == "observed" and not lineage.get(source) and not response_ids:
                    raise ValueError("계산값에 해당하는 원문이 없습니다.")
                comparison = {
                    "rubric_version": "v0.8",
                    "input_versions": version or {},
                    "grade_boundaries": {
                        "r": [0.8, 0.95, 1.05, 1.2],
                        "p": [20, 40, 60, 80],
                        "q": [0.5, 0.8, 1.2, 1.5],
                        "yoy": [-10, -3, 3, 10],
                    },
                    "interpretation": value if isinstance(value, dict) else {},
                    "spatial_scope": "원문 요청 범위",
                    "reason": score["reason"],
                }
                fact = register_fact(
                    scope,
                    industry_code=row["code"],
                    source=source if score["status"] != "n.a." else "baseline",
                    metric=metric,
                    value=value.get("r", value) if isinstance(value, dict) else value,
                    unit=unit,
                    status=score["status"],
                    row_ids=refs,
                    response_ids=response_ids,
                    comparison=comparison,
                    period=version.get("periods", {}).get(source, "승인 기준선·프로필")
                    if version
                    else "승인 기준선·프로필",
                    connection=db,
                )
                facts_by_item[(row["code"], item)] = [fact]
                if item == "D1" and score["status"] == "observed" and isinstance(value, dict):
                    scale = register_fact(
                        scope,
                        industry_code=row["code"],
                        source=source,
                        metric="pattern_scale_percentile",
                        value=value["p"],
                        unit="백분위",
                        status="observed",
                        row_ids=refs,
                        response_ids=response_ids,
                        comparison=comparison,
                        connection=db,
                    )
                    facts_by_item[(row["code"], item)].append(scale)
        db.execute(
            "INSERT INTO score_snapshots VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                score_id,
                scope.request_id,
                scope.snapshot_id,
                scope.run_id,
                "v0.8",
                CALC_VERSION,
                _json(report["rows"]),
                _json([r["code"] for r in report["top5"]]),
                "unreviewed",
                _now(),
            ),
        )
        for row in report["rows"]:
            for item, score in row["items"].items():
                db.execute(
                    "INSERT INTO scores VALUES(?,?,?,?,?,?,?,?)",
                    (
                        score_id,
                        row["code"],
                        item,
                        WEIGHTS[item],
                        score["status"],
                        score["grade"],
                        score["points"],
                        _json(facts_by_item[(row["code"], item)]),
                    ),
                )
    return score_id


def persist_input_facts(scope, data, lineage, responses, version):
    """기존 formatter가 만든 원 지표도 조회할 수 있게 저장합니다. 수식은 추가하지 않습니다."""
    response_refs = {}
    for response in responses:
        response_refs.setdefault(response["source"], []).append(response["response_id"])
    operands = []
    for row in data.get("commercial_area", {}).get("by_middle", []):
        for key, metric, unit in [
            ("count", "store_count", "개"),
            ("density_per_km2", "density_per_km2", "개/km²"),
            ("lq", "lq", "배수"),
            ("jacobian", "differentiation", "유효 업종 수"),
        ]:
            operands.append((row["code"], "commercial_area", metric, row.get(key), unit))
    for row in data.get("business_lifecycle", {}).get("industries", []):
        for metric, unit in [
            ("avg_store_count", "개"),
            ("recent_year_close_rate", "%"),
            ("oldest_year_close_rate", "%"),
            ("net_change_rate", "%"),
            ("turnover_rate", "%"),
        ]:
            operands.append(
                (row["industry_id"], "business_lifecycle", metric, row["metrics"].get(metric), unit)
            )
    fp = data.get("floating_population", {})
    operands.extend(
        [
            (
                None,
                "floating_population",
                "mean_daily_per_trade_area",
                fp.get("benchmark", {}).get("mean_daily_per_trade_area"),
                "명/일·상권 1곳",
            ),
            (
                None,
                "floating_population",
                "weekend_index",
                fp.get("benchmark", {}).get("weekend_index"),
                "배수",
            ),
            (
                None,
                "floating_population",
                "age_share",
                fp.get("population", {}).get("age_share"),
                "비율",
            ),
            (
                None,
                "floating_population",
                "by_time",
                fp.get("population", {}).get("by_time"),
                "분기 통행량",
            ),
            (
                None,
                "floating_population",
                "yoy_change",
                fp.get("trend", {}).get("yoy_change"),
                "비율",
            ),
        ]
    )
    with connect(scope.path) as db:
        for code, source, metric, value, unit in operands:
            known = value is not None and source not in data.get("runtime_partial_sources", [])
            refs = (
                list(
                    lineage.get("industry_rows", {})
                    .get(source, {})
                    .get(code, lineage.get(source, []))
                )
                if known
                else []
            )
            # LQ와 차별화는 전체 점포 구성·비교 범위의 원문도 필요합니다.
            if metric in {"lq", "differentiation"} and known:
                refs = list(lineage.get(source, []))
            refs.extend(lineage.get("baseline", []))
            response_ids = response_refs.get(source, [])
            register_fact(
                scope,
                industry_code=code,
                source=source,
                metric=metric,
                value=value,
                unit=unit,
                status="observed" if known else "unknown",
                row_ids=refs,
                response_ids=response_ids,
                comparison={"input_versions": version, "calculation": "기존 분석 함수 출력"},
                period=version["periods"].get(source, "원문 시점"),
                connection=db,
            )


def _persist(task, scope, education_scan=None):
    scan = education_scan.model_dump(mode="json") if education_scan is not None else {}
    if scan:
        # 기존 기본 조회는 geometry를 받지 않으므로 구역이 있으면 좌표 포함은 미확인입니다.
        scan["contains_verified"] = not scan.get("zones") and scan.get("status") == "ok"
        scope.record_sync(
            source="regulation",
            source_type="api",
            args={"origin": "validated_education_zone_scan"},
            page="node",
            status=None,
            payload={"rows": [scan]},
            secrets=[os.getenv("VWORLD_API_KEY", "")],
        )
    data, lineage, responses = format_snapshot(task, scope)
    data["education_zones"] = scan
    profiles, versions, config_rows = _config(scope)
    lineage["baseline"], lineage["profiles"] = config_rows
    versions["periods"] = {
        "floating_population": data.get("floating_population", {}).get("period_code", "자료 없음"),
        "business_lifecycle": data.get("business_lifecycle", {})
        .get("metadata", {})
        .get("base_quarter", "자료 없음"),
        "commercial_area": "현재 점포 스냅샷(원래 수집 시각은 원문 참조)",
        "map": "지도 관측 시각",
        "resident_population": (data.get("floating_population", {}).get("resident") or {}).get(
            "period_code", "자료 없음"
        ),
        "worker_population": (data.get("floating_population", {}).get("worker") or {}).get(
            "period_code", "자료 없음"
        ),
    }
    versions["spatial_scope"] = {
        "radius_m": task.radius_m,
        "latitude": task.site.latitude,
        "longitude": task.site.longitude,
        "selected_trade_area_codes": data.get("selected_trade_area_codes", []),
    }
    # 계산 데이터만 사용하며 기존 decision 입력·결과는 변경하지 않습니다.
    persist_input_facts(scope, data, lineage, responses, versions)
    report = evaluate(data, profile_rows=profiles)
    return persist_report(scope, report, lineage, responses, versions)


async def persist_snapshot_scores(task, education_scan=None):
    scope = current_capture()
    if scope is None:
        return None
    try:
        return await _write(_persist, task, scope, education_scan)
    except Exception:
        raise RawStorageError("사실·코드 점수 생성 또는 저장에 실패했습니다.") from None
