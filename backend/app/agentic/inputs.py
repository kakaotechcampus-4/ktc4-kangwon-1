"""원문 스냅샷을 기존 계산 함수로 변환합니다. API·LLM 호출 경로는 없습니다."""

import json
from collections import defaultdict

import pandas as pd

from app.agents.business_lifecycle.client import normalize_row
from app.agents.business_lifecycle.preprocess import aggregate_rows
from app.agents.commercial_area.client import SbizApiError, check_header, extract_items, to_store
from app.agents.commercial_area.industries import (
    incomplete_split_codes,
    load_middle_master,
    map_stores,
)
from app.agents.commercial_area.metrics import build_middle_rows, count_by_middle
from app.agents.floating_population.geo import overlapping_areas
from app.agents.floating_population.metrics import aggregate, daily_benchmark, trend
from app.agents.floating_population.models import (
    FlpopRecord,
    PopulationRecord,
    TrdarArea,
    quarter_days,
)
from app.agents.floating_population.numeric import complete_sum
from app.agents.floating_population.population import (
    RESIDENT_KIND,
    WORKER_KIND,
    age_share,
    resident_block,
    worker_block,
)
from app.db.connection import connect
from app.geo import to_epsg5181
from app.industries.catalog import SEOUL_TO_INDUSTRY
from app.industries.lookup import service_code


def to_float(value):
    """pandas 결측을 없애고 기존 보고 자료의 소수 두 자리 규칙을 유지합니다."""
    return None if pd.isna(value) else round(float(value), 2)


def load_raw(scope):
    with connect(scope.path) as db:
        responses = [
            dict(r)
            for r in db.execute(
                "SELECT p.*,b.response_json FROM raw_responses p "
                "JOIN raw_payloads b USING(payload_hash) "
                "WHERE p.snapshot_id=? AND p.duplicate_of IS NULL",
                (scope.snapshot_id,),
            )
        ]
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT r.*,p.source,p.run_id,p.request_args_json,p.group_key FROM "
                "raw_rows r JOIN raw_response_rows e USING(raw_row_id) "
                "JOIN raw_responses p USING(response_id) WHERE p.snapshot_id=? "
                "AND p.duplicate_of IS NULL AND e.duplicate_of IS NULL",
                (scope.snapshot_id,),
            )
        ]
    # 큰 원문 BLOB을 SQL에서 정렬하면 불필요한 임시 파일이 생깁니다.
    responses.sort(key=lambda r: (r["collected_at"], r["response_id"]))
    # 같은 원천의 재수집을 이전 관측과 섞지 않고 원천별 최신 run을 선택합니다.
    runs = {r["source"]: r["run_id"] for r in responses}
    responses = [r for r in responses if r["run_id"] == runs[r["source"]]]
    rows = [r for r in rows if r["run_id"] == runs[r["source"]]]
    grouped = defaultdict(list)
    for r in rows:
        r["row"] = json.loads(r["raw_json"])
        r["args"] = json.loads(r["request_args_json"])
        grouped[r["source"]].append(r)
    partial = set()
    groups = defaultdict(list)
    for r in responses:
        groups[(r["source"], r["group_key"])].append(r)
        if r["http_status"] is not None and r["http_status"] >= 400:
            partial.add(r["source"])
    for (source, group), pages in groups.items():
        expected = max(
            (p["expected_rows"] for p in pages if p["expected_rows"] is not None), default=None
        )
        count = sum(r["group_key"] == group for r in grouped[source])
        if expected is not None and count < expected:
            partial.add(source)
    return grouped, responses, partial


def _unique(rows, keys):
    unique = {}
    for r in rows:
        key = tuple(str(r["row"].get(k, "")) for k in keys)
        if key in unique and unique[key]["row"] != r["row"]:
            raise ValueError("원문 자연키에 상충하는 값이 있습니다.")
        unique[key] = r
    return list(unique.values())


def format_snapshot(task, scope):
    return format_inputs(task, *load_raw(scope))


def format_inputs(task, raw, responses, partial, *, district_counts=None, periods=None):
    """전송/저장과 분리한 기존 계산 경로. 로컬 어댑터도 같은 함수를 호출합니다."""
    data = {
        "address": task.site.input_address,
        "runtime_partial_sources": sorted(partial),
        "population_baselines": {RESIDENT_KIND: {}, WORKER_KIND: {}},
    }
    lineage = {
        "floating_population": [],
        "commercial_area": [],
        "business_lifecycle": [],
        "map": [],
        "regulation": [],
    }
    store_rows = [
        r
        for r in raw["commercial_area"]
        if r["args"].get("query", {}).get("radius") == task.radius_m
        and abs(float(r["args"]["query"].get("cx", 0)) - round(task.site.longitude, 6)) < 1e-7
        and abs(float(r["args"]["query"].get("cy", 0)) - round(task.site.latitude, 6)) < 1e-7
    ]
    store_rows = _unique(store_rows, ["bizesId"])
    collection = [
        r
        for r in responses
        if r["source"] == "commercial_area"
        and json.loads(r["request_args_json"]).get("query", {}).get("radius") == task.radius_m
    ]
    if collection:
        try:
            for page in collection:
                check_header(json.loads(page["response_json"]))
                extract_items(json.loads(page["response_json"]))
        except SbizApiError:
            partial.add("commercial_area")
            data["runtime_partial_sources"] = sorted(partial)
        stores = [s for r in store_rows if (s := to_store(r["row"])) is not None]
        data["commercial_split_missing"] = sorted(incomplete_split_codes(stores))
        data["commercial_collection_complete"] = "commercial_area" not in partial
        mapped = map_stores(stores)
        larger = [
            r
            for r in raw["commercial_area"]
            if r["args"].get("query", {}).get("radius", 0) > task.radius_m
        ]
        baseline_counts = None
        if larger:
            group = larger[0]["group_key"]
            larger = _unique([r for r in larger if r["group_key"] == group], ["bizesId"])
            base_stores = [s for r in larger if (s := to_store(r["row"])) is not None]
            baseline_counts = count_by_middle(map_stores(base_stores))
        data["commercial_area"] = {
            "radius_m": task.radius_m,
            "by_middle": [
                r.model_dump(mode="json")
                for r in build_middle_rows(
                    mapped,
                    task.radius_m,
                    load_middle_master(),
                    baseline_counts=baseline_counts,
                    district_counts=district_counts,
                )
            ],
        }
        lineage["commercial_area"] = [
            r["raw_row_id"] for r in store_rows if r["raw_row_id"] is not None
        ]
    lineage["industry_rows"] = {"commercial_area": {}, "business_lifecycle": {}}
    for row in store_rows:
        if row["raw_row_id"] is None:
            continue
        code = service_code(row["row"].get("indsMclsCd", ""), row["row"].get("indsSclsCd"))
        if code:
            lineage["industry_rows"]["commercial_area"].setdefault(code, []).append(
                row["raw_row_id"]
            )
    areas = [
        TrdarArea.from_api_row(r["row"])
        for r in raw["floating_population"]
        if "XCNTS_VALUE" in r["row"] and "YDNTS_VALUE" in r["row"]
    ]
    hits = (
        overlapping_areas(
            areas, *to_epsg5181(task.site.latitude, task.site.longitude), task.radius_m
        )
        if areas
        else []
    )
    codes = {a.trdar_cd for a, _ in hits}
    fp_rows = _unique(
        [
            r
            for r in raw["floating_population"]
            if "STDR_YYQU_CD" in r["row"]
            and not r["args"].get("probe")
            and str(r["row"].get("TRDAR_CD")) in codes
        ],
        ["STDR_YYQU_CD", "TRDAR_CD"],
    )
    if fp_rows:
        series = defaultdict(list)
        for r in fp_rows:
            record = FlpopRecord.from_api_row(r["row"])
            series[record.stdr_yyqu_cd].append(record)
        latest = (periods or {}).get("floating") or max(series)
        series.setdefault(latest, [])
        quarters = sorted(series)
        records = series[latest]
        pop = aggregate(records, latest)
        warnings = []
        data["floating_population"] = {
            "period_code": latest,
            "population": pop.model_dump(mode="json"),
            "benchmark": daily_benchmark(
                pop, complete_sum(r.total for r in records), len(records), quarter_days(latest)
            ).model_dump(mode="json"),
            "reliability": {"covered_trade_areas": len(records)},
            "trend": trend([(q, series[q]) for q in quarters], codes, warnings).model_dump(
                mode="json"
            ),
        }
        data["floating_warnings"] = warnings
        lineage["floating_population"] = [
            r["raw_row_id"] for r in fp_rows if r["raw_row_id"] is not None
        ]
        for source, kind, key, builder in [
            ("resident_population", RESIDENT_KIND, "resident", resident_block),
            ("worker_population", WORKER_KIND, "worker", worker_block),
        ]:
            rows = raw[source]
            records = [PopulationRecord.from_api_row(r["row"], kind) for r in rows]
            data["population_baselines"][kind] = age_share(records) if records else {}
            if records:
                block = builder(records, records[0].stdr_yyqu_cd, codes)
                data["floating_population"][key] = block.model_dump(mode="json") if block else None
                lineage[source] = [r["raw_row_id"] for r in rows if r["raw_row_id"] is not None]

    lifecycle = _unique(raw["business_lifecycle"], ["STDR_YYQU_CD", "TRDAR_CD", "SVC_INDUTY_CD"])
    if lifecycle:
        area_codes = {str(r["row"].get("TRDAR_CD")) for r in lifecycle}
        if len(area_codes) != 1:
            raise ValueError("개폐업 원문에 여러 상권이 섞였습니다.")
        area = next(iter(area_codes))
        base = (periods or {}).get("lifecycle") or max(
            str(r["row"]["STDR_YYQU_CD"]) for r in lifecycle
        )
        requested = {
            json.loads(r["request_args_json"]).get("extra", "").split("/")[0]
            for r in responses
            if r["source"] == "business_lifecycle"
        }
        requested = {q for q in requested if len(q) == 5 and q.isdigit() and q <= base}
        count = len(requested) or 12
        frame = aggregate_rows([normalize_row(r["row"]) for r in lifecycle], area, base, count)
        metrics = [
            "avg_store_count",
            "recent_year_close_rate",
            "oldest_year_close_rate",
            "net_change_rate",
            "turnover_rate",
        ]
        data["business_lifecycle"] = {
            "metadata": {"base_quarter": base, "quarter_count": count},
            "industries": [
                {
                    "industry_id": r["service_id"],
                    "data_complete": bool(r["data_complete"]),
                    "zero_filled_sources": int(r["zero_filled_sources"]),
                    "metrics": {key: to_float(r[key]) for key in metrics},
                }
                for r in frame.to_dict("records")
            ],
        }
        data["lifecycle_quarterly"] = frame.attrs["quarterly_detail"]
        lineage["business_lifecycle"] = [
            r["raw_row_id"] for r in lifecycle if r["raw_row_id"] is not None
        ]
        for row in lifecycle:
            if row["raw_row_id"] is None:
                continue
            code = SEOUL_TO_INDUSTRY.get(row["row"].get("SVC_INDUTY_CD"))
            if code:
                lineage["industry_rows"]["business_lifecycle"].setdefault(code, []).append(
                    row["raw_row_id"]
                )
    lineage["regulation"] = [r["raw_row_id"] for r in raw["regulation"]]
    data["selected_trade_area_codes"] = sorted(codes)
    return data, lineage, responses
