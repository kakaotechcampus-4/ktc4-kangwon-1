"""미관측 시설을 꾸미지 않고 고정90점 두 후보를 새 위치에서 비교합니다."""

import argparse
import json
import math
from pathlib import Path

from app.agentic.scoring import profiles
from app.agents.floating_population.geo import overlapping_areas
from app.geo import to_epsg5181
from app.industries.catalog import INDUSTRIES, INDUSTRIES_WITHOUT_SEOUL
from backtest.c4_blend_comparison import metrics_for
from backtest.c4_policy import observe_components
from backtest.customer_trend import evidence_for
from backtest.customer_trend_comparison import customer_panels
from backtest.demand_trend import d4_fraction
from backtest.frozen_quantile import score_candidate
from backtest.licensing import sha256
from backtest.offline import block_network, write_json
from backtest.past80 import init_worker, score_site
from backtest.past_baselines import build as build_baselines
from backtest.score90 import Score90Configuration, score90
from backtest.weight_selection import order_scores

CONFIG = Score90Configuration(30, "equal")
METHODS = ("control_actual90", "customer_half_actual90", "popular")


def rank_bounds(intervals: dict, ties: dict) -> dict:
    if (
        not intervals
        or set(intervals) != set(ties)
        or any(
            set(v) != {"low", "high"}
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in v.values())
            or not 0 <= v["low"] <= v["high"] <= 90 + 1e-9
            for v in intervals.values()
        )
    ):
        raise ValueError("모든 후보의 유효한 90점 구간과 동점 기준이 필요합니다.")
    result = {}
    # 상대 업종의 모든 시설 점수가 동시에 유리·불리하다고 가정한 보수적 순위 범위입니다.
    for code in intervals:
        optimistic = {c: v["high" if c == code else "low"] for c, v in intervals.items()}
        pessimistic = {c: v["low" if c == code else "high"] for c, v in intervals.items()}
        best = order_scores(optimistic, ties).index(code) + 1
        worst = order_scores(pessimistic, ties).index(code) + 1
        result[code] = {"best_rank": best, "worst_rank": worst}
    return result


def calculate(saved, calibration, background, areas, panels, city_cache, components=None):
    base = score_candidate(saved, calibration, background)
    catalog = profiles()
    site = saved["site"]
    codes = [
        a.trdar_cd
        for a, _ in overlapping_areas(areas, *to_epsg5181(site["latitude"], site["longitude"]), 500)
    ]
    source = {c: evidence_for(p, codes, panels, city_cache) for c, p in catalog.items()}
    components = (
        components
        if components is not None
        else {
            c: observe_components(p, c, {"data": {"queries": {}, "places": {}}})
            for c, p in catalog.items()
        }
    )
    details, intervals = {}, {}
    for method in METHODS[:2]:
        details[method], intervals[method] = {}, {}
        for code, feature in base["details"].items():
            fractions = dict(feature["fractions"])
            e = source[code]
            if (
                method == "customer_half_actual90"
                and e["available"]
                and feature["original_status"]["D4"] == "observed"
            ):
                fractions["D4"] = (fractions["D4"] + d4_fraction(e["local"]["yoy"])) / 2
            observed = components[code]
            details[method][code] = score90(
                fractions,
                feature["original_status"],
                catalog[code],
                observed,
                CONFIG,
            )
            intervals[method][code] = {}
            for endpoint, points in (("low", 0), ("high", 10)):
                # 미확인 시설의 원문은 그대로 두고 민감도 계산 안에서만 양 끝을 가정합니다.
                hypothetical = {
                    k: v if v["status"] == "observed" else {"status": "observed", "points": points}
                    for k, v in observed.items()
                }
                intervals[method][code][endpoint] = score90(
                    fractions,
                    feature["original_status"],
                    catalog[code],
                    hypothetical,
                    CONFIG,
                )["normalized"]
            value = details[method][code]["normalized"]
            if (
                not intervals[method][code]["low"] - 1e-10
                <= value
                <= intervals[method][code]["high"] + 1e-10
            ):
                raise ValueError("미확인 시설의 정책 기여가 시설 점수 범위를 벗어났습니다.")
    ties = {
        r["code"]: {"coverage": r["coverage"], "adjustment": r["space"]["adjustment"]}
        for r in saved["scores"]
    }
    values = {m: {c: d["normalized"] for c, d in rows.items()} for m, rows in details.items()}
    orders = {m: order_scores(v, ties) for m, v in values.items()}
    counts = {r["code"]: r["count"] for r in saved["data"]["commercial_area"]["by_middle"]}
    orders["popular"] = sorted(counts, key=lambda c: (-counts[c], c))
    return {
        "values": values,
        "orders": orders,
        "details": details,
        "C4_components": components,
        "hypothetical_C4_score_intervals": intervals,
        "C4_rank_sensitivity": {
            scope: {
                m: rank_bounds(
                    {c: v for c, v in row.items() if c in universe},
                    {c: v for c, v in ties.items() if c in universe},
                )
                for m, row in intervals.items()
            }
            for scope, universe in (
                ("all_51", set(INDUSTRIES)),
                ("supported_45", set(INDUSTRIES) - set(INDUSTRIES_WITHOUT_SEOUL)),
            )
        },
        "actual_customer_source_evidence": source,
    }


def run(analysis, cohort, data, current, out):
    root = cohort.parent
    protocol = json.loads((root / "preselection-protocol.json").read_text(encoding="utf-8"))
    for name, expected in protocol["scoring_rule_sha256"].items():
        path = (
            Path("app/industries/data") / name if name.endswith(".csv") else Path("backtest") / name
        )
        if sha256(path) != expected:
            raise ValueError("표본 선정 전에 고정한 계산식이 변경되었습니다: " + name)
    selected = json.loads(cohort.read_text(encoding="utf-8"))
    if out.exists() or not selected["sites"] or not selected["selected_before_any_model_scores"]:
        raise ValueError("점수 전에 선정한 새 위치와 새 결과 경로가 필요합니다.")
    out.mkdir(parents=True)
    (out / "scores").mkdir()
    historical = analysis / "20261027/past80-location-comparison"
    background = json.loads(
        (analysis / "20261026/historical-competition-20252/samples.json").read_text(
            encoding="utf-8"
        )
    )
    background["reference_quarter"] = "20252"
    calibration = build_baselines(
        data,
        current,
        analysis / "20261027/past80-source",
        analysis / "20261026/historical-competition-20252",
    )
    original_calibration = json.loads((historical / "baselines.json").read_text(encoding="utf-8"))
    if json.loads(json.dumps(calibration)) != original_calibration:
        raise ValueError("고정한 과거 기준선이 재현되지 않습니다.")
    init_worker(str(data), calibration)
    areas, panels, source_metadata = customer_panels(
        data, analysis / "20261030/customer-population-history"
    )
    original = json.loads((historical / "scores/SV001-1.json").read_text(encoding="utf-8"))
    replay = score_site(
        {"id": "SV001-1", "site": original["site"], "target_industry_code": original["target"]}
    )
    if replay["orders"] != original["orders"]:
        raise ValueError("과거 원표본의 전체 분석 순위가 재현되지 않습니다.")
    city_cache, replay_checks = {}, 0
    for case_id in ("SV001-1", "SV016-1", "SV027-5", "SV030-2", "SV040-1"):
        saved = json.loads((historical / "scores" / f"{case_id}.json").read_text(encoding="utf-8"))
        expected = json.loads(
            (
                analysis
                / "20261030/true90-matched-customer-trend-validation/scores"
                / f"{case_id}.json"
            ).read_text(encoding="utf-8")
        )
        facilities = json.loads(
            (
                analysis / "20261030/true90-survival-item-validation/scores" / f"{case_id}.json"
            ).read_text(encoding="utf-8")
        )["facility_components"]
        calc = calculate(saved, calibration, background, areas, panels, city_cache, facilities)
        for method, prior in (
            ("control_actual90", "control"),
            ("customer_half_actual90", "customer_half"),
        ):
            for code, value in calc["values"][method].items():
                if not math.isclose(value, expected["values"][prior][code], abs_tol=1e-10):
                    raise ValueError("기존90점 두 후보가 재현되지 않습니다.")
                replay_checks += 1
    write_json(
        out / "design.json",
        {
            "protocol": protocol,
            "cohort_sha256": sha256(cohort),
            "new_facility_measurements": 0,
            "C4_unknown_is_not_observed_zero": True,
            "all_unknown_C4_max_still_10": True,
            "replayed_previous_actual90_scores": replay_checks,
            "old_analysis_pipeline_replayed": True,
            "source_metadata": source_metadata,
            "runner_sha256": sha256(Path(__file__)),
            "LLM_calls": 0,
            "map_calls": 0,
            "external_http_requests": 0,
        },
    )
    cases, orders = [], {}
    for site in selected["sites"]:
        saved = score_site(site)
        if saved["data"]["area_selection"]["area_code"] != site["area"]:
            raise ValueError("표본 선정과 분석의 상권이 다릅니다.")
        calculated = calculate(saved, calibration, background, areas, panels, city_cache)
        row = {
            "id": site["id"],
            "target": site["target_industry_code"],
            "site": site["site"],
            "cluster": site["area"],
            "orders": calculated["orders"],
            "C4_target_rank_sensitivity": {
                scope: {m: intervals[row_code] for m, intervals in methods.items()}
                for scope, methods in calculated["C4_rank_sensitivity"].items()
                if (row_code := site["target_industry_code"]) in next(iter(methods.values()))
            },
        }
        write_json(
            out / "scores" / f"{site['id']}.json", {"input": saved, "calculated": calculated}
        )
        cases.append(row)
        orders[site["id"]] = row["orders"]
    results = {
        "n": len(cases),
        "cases": cases,
        "metrics": metrics_for(cases, orders, METHODS),
        "new_spatial_validation": True,
        "methods_changed_after_results": False,
        "C4_not_measured_policy_estimates_only": True,
        "all_industry_generalization_established": False,
        "original212_or184_goal_metrics_changed": False,
        "operating_applied": False,
        "LLM_calls": 0,
        "map_calls": 0,
        "external_http_requests": 0,
        "replayed_previous_actual90_scores": replay_checks,
        "provenance": {"cohort_sha256": sha256(cohort), "data_sha256": sha256(data)},
    }
    write_json(out / "results.json", results)
    return {
        "n": len(cases),
        "cases": [
            {
                "id": c["id"],
                "target": c["target"],
                "ranks": {m: o.index(c["target"]) + 1 for m, o in c["orders"].items()},
                "C4_rank_sensitivity": c["C4_target_rank_sensitivity"],
            }
            for c in cases
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("analysis", "cohort", "data", "current", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    with block_network():
        result = run(**vars(parser.parse_args()))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
