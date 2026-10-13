"""저장된 API 점포와 서울 CSV를 같은 주소·500m·51업종 기준으로 비교한다."""

from __future__ import annotations

import argparse
import json
import sys
from bisect import bisect_right
from collections import Counter
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.commercial_area.baseline import (  # noqa: E402
    SEOUL_INDUSTRY_DENSITY_PERCENTILES,
    industry_percentile,
)
from app.agents.commercial_area.client import to_store  # noqa: E402
from app.agents.commercial_area.metrics import haversine_m  # noqa: E402
from app.agents.commercial_area.trade_areas import SeoulTradeArea, load_trade_areas  # noqa: E402
from app.agents.floating_population.baseline import DAILY_TOTAL_PERCENTILES  # noqa: E402
from app.geo import to_epsg5181  # noqa: E402
from scripts.build_density_baseline import (  # noqa: E402
    area_km2,
    industry_counts,
    load_industry_done,
    percentile_table,
    sample_csv,
)
from scripts.rubric_dryrun import evaluate, result, summarize, valid  # noqa: E402


def alternatives(samples: list[dict]) -> dict:
    """C1만 바꿔 대안을 비교하며 나머지 문항·판정 조건은 고정한다."""
    areas = {a.code: a for a in load_trade_areas()}
    grouped = {}
    for code, row in load_industry_done().items():
        if code not in areas:
            continue
        counts = json.loads(row["counts"])
        blocked = json.loads(row["blocked_codes"])
        for industry, count in counts.items():
            if industry not in blocked:
                grouped.setdefault((areas[code].kind, industry), []).append(count / area_km2(500))
    medians = {key: percentile_table(vals)[9] for key, vals in grouped.items()}
    variants = {"current": [], "type_median": [], "percentile": [], "demand": [], "type_demand": []}
    demand_ratios = []
    for sample in samples:
        base = evaluate(sample, c1_alpha=0)
        kind = areas[sample["business_lifecycle"]["metadata"]["area_resolver"]["area_code"]].kind
        densities = {
            r["code"]: r["density_per_km2"] for r in sample["commercial_area"]["by_middle"]
        }
        daily = (
            sample.get("floating_population", {})
            .get("benchmark", {})
            .get("mean_daily_per_trade_area")
        )
        demand_ratio = daily / DAILY_TOTAL_PERCENTILES[50] if valid(daily) and daily > 0 else None
        demand_ratios.append(
            {"address": base["address"], "daily_population": daily, "demand_ratio": demand_ratio}
        )
        variants["current"].append(base)
        for variant in ("type_median", "percentile", "demand", "type_demand"):
            rows = []
            for row in base["rows"]:
                code = row["code"]
                items = deepcopy(row["items"])
                if items["C1"]["status"] == "observed":
                    if variant != "percentile":
                        median = (
                            medians[kind, code]
                            if variant in {"type_median", "type_demand"}
                            else SEOUL_INDUSTRY_DENSITY_PERCENTILES[code][50]
                        )
                        divisor = demand_ratio if variant in {"demand", "type_demand"} else 1
                        q = (
                            densities[code] / median / divisor
                            if median >= 0.01 and divisor
                            else None
                        )
                        items["C1"] = (
                            result(
                                "C1",
                                4 - bisect_right([0.5, 0.8, 1.2, 1.5], q),
                                value=q,
                                reason=f"시험 {variant}; 유형={kind}; 유동 비율={demand_ratio}",
                            )
                            if q is not None
                            else result("C1", reason="중앙 밀도 또는 유동 규모 결측·0")
                        )
                    else:
                        percentile = industry_percentile(code, densities[code])
                        items["C1"] = result(
                            "C1",
                            4 - bisect_right([20, 40, 60, 80], percentile),
                            value=percentile,
                            reason="서울 업종별 백분위",
                        )
                rows.append(summarize(code, items, row["regulation"]))
            variants[variant].append(
                {
                    "address": base["address"],
                    "kind": kind,
                    "rows": rows,
                    "badges": dict(Counter(r["badge"] for r in rows)),
                }
            )
    food = {"I201", "I202", "I203", "I204", "I210"}
    tables = {}
    for name, reports in variants.items():
        rows = [r for report in reports for r in report["rows"]]
        tables[name] = {
            "all_c1_grades": dict(Counter(str(r["items"]["C1"]["grade"]) for r in rows)),
            "food_c1_grades": dict(
                Counter(str(r["items"]["C1"]["grade"]) for r in rows if r["code"] in food)
            ),
            "food_badges": dict(Counter(r["badge"] for r in rows if r["code"] in food)),
            "all_badges": dict(Counter(r["badge"] for r in rows)),
        }
    return {
        "comparisons": tables,
        "demand_ratios": demand_ratios,
        "seoul_daily_median": DAILY_TOTAL_PERCENTILES[50],
        "reports": variants,
        "type_sample_counts": dict(Counter(a.kind for a in areas.values())),
        "type_assignment": (
            "기존 개폐업 포함/300m 최근접 상권 유형. 겹친 유형을 단일 대표로 고른 시험 가정"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seoul-csv", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "cache"
    samples = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((root / "rubric_samples").glob("sample-*.json"))
    ]
    areas = tuple(
        SeoulTradeArea(
            str(i),
            s["address"],
            "",
            "",
            "",
            *to_epsg5181(s["site"]["latitude"], s["site"]["longitude"]),
            0,
        )
        for i, s in enumerate(samples, 1)
    )
    csv_rows = sample_csv(args.seoul_csv, "20262", areas)
    output = []
    for sample, csv_row in zip(samples, csv_rows, strict=True):
        site = sample["site"]
        lat, lon = site["latitude"], site["longitude"]
        cache = json.loads(
            (root / f"radius_500_{round(lat, 6)}_{round(lon, 6)}.json").read_text(encoding="utf-8")
        )
        stores = [to_store(row) for row in cache["items"]]
        stores = [s for s in stores if s is not None]
        api_counts, _ = industry_counts(stores)
        assert all(
            api_counts[r["code"]] == r["count"] for r in sample["commercial_area"]["by_middle"]
        )
        assert all(
            abs(r["density_per_km2"] - r["count"] / area_km2(500)) <= 0.0001
            for r in sample["commercial_area"]["by_middle"]
        )
        csv_counts = json.loads(csv_row["counts"])
        outside = [s for s in stores if haversine_m(lat, lon, s.latitude, s.longitude) > 500]
        inside_counts, _ = industry_counts([s for s in stores if s not in outside])
        ids = Counter(s.store_id for s in stores)
        rows = []
        for row in sample["commercial_area"]["by_middle"]:
            code = row["code"]
            api, csv = api_counts[code], csv_counts[code]
            rows.append(
                {
                    "code": code,
                    "api_count": api,
                    "csv_count": csv,
                    "api_density": row["density_per_km2"],
                    "csv_density": csv / area_km2(500),
                    "api_csv_ratio": api / csv if csv else None,
                    "inside_api_count": inside_counts[code],
                }
            )
        output.append(
            {
                "address": sample["address"],
                "api_meta": cache["meta"],
                "api_raw_count": len(stores),
                "csv_raw_count": csv_row["raw_store_count"],
                "duplicate_api_ids": sum(v - 1 for v in ids.values()),
                "api_outside_500m": len(outside),
                "api_mapping_matches_trial": all(
                    api_counts[r["code"]] == r["count"]
                    for r in sample["commercial_area"]["by_middle"]
                ),
                "rows": rows,
            }
        )
    path = root / "rubric_samples/c1-density-audit.json"
    path.write_text(
        json.dumps(
            {
                "source": str(args.seoul_csv),
                "http_calls": 0,
                "llm_calls": 0,
                "addresses": output,
                "alternatives": alternatives(samples),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(path)


if __name__ == "__main__":
    main()
