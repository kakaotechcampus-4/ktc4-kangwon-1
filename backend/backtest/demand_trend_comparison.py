"""업종 관련 통행량 증감의 D4를 C4 포함90점에서 비교합니다."""

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from app.agentic.scoring import profiles
from app.agents.floating_population.geo import overlapping_areas
from app.agents.floating_population.models import FlpopRecord
from app.db.connection import readonly
from app.geo import to_epsg5181
from app.industries.catalog import INDUSTRIES
from backtest.c4_blend_comparison import metrics_for, validate_split
from backtest.demand_trend import MODES, QUARTERS, d4_fraction, replacement, segment_changes
from backtest.licensing import sha256
from backtest.offline import block_network, write_json
from backtest.score90 import Score90Configuration, score90
from backtest.score90_comparison import ANCHOR, choose
from backtest.score90_demand import load_population
from backtest.weight_selection import order_scores

CONFIG = Score90Configuration(30, "equal")


def load_history(data):
    areas, _, metadata = load_population(data)
    panels = {}
    versions = {}
    with readonly(data) as db:
        for quarter in QUARTERS:
            rows = db.execute(
                "SELECT v.*,f.columns_json FROM data_versions v "
                "JOIN source_fields f USING(version_id) "
                "WHERE v.source='floating' AND v.quarter=? AND v.state='active'",
                (quarter,),
            ).fetchall()
            if len(rows) != 1:
                raise ValueError("두 분기의 고정 인구 자료가 하나씩 필요합니다.")
            version = dict(rows[0])
            columns = json.loads(version["columns_json"])
            records = [
                FlpopRecord.from_api_row(dict(zip(columns, json.loads(r[0]), strict=True)))
                for r in db.execute(
                    "SELECT payload FROM floating WHERE version_id=?", (version["version_id"],)
                )
            ]
            if len(records) != len({r.trdar_cd for r in records}) or {
                r.stdr_yyqu_cd for r in records
            } != {quarter}:
                raise ValueError("동일 분기의 중복 없는 실제 행이 필요합니다.")
            panels[quarter] = {r.trdar_cd: r for r in records}
            versions[quarter] = version
    return areas, panels, {"floating": versions, "areas": metadata["areas"]}


def run(source, historical, data, splits, out):
    if out.exists():
        raise ValueError("기존 D4 실험 결과는 덮어쓰지 않습니다.")
    out.mkdir(parents=True)
    (out / "scores").mkdir()
    previous = json.loads((source / "results.json").read_text(encoding="utf-8"))
    reference = json.loads((historical / "results.json").read_text(encoding="utf-8"))
    cases = [{k: c[k] for k in ("id", "target", "site", "cluster")} for c in reference["cases"]]
    spatial = json.loads(splits.read_text(encoding="utf-8"))
    catalog = profiles()
    if len(cases) != 212 or set(spatial["assignments"]) != {c["id"] for c in cases}:
        raise ValueError("고정212곳과 지역 분리가 필요합니다.")
    areas, panels, versions = load_history(data)
    hashes = {
        "source": sha256(source / "results.json"),
        "historical": sha256(historical / "results.json"),
        "splits": sha256(splits),
        "scorer": sha256(Path("backtest/demand_trend.py")),
        "runner": sha256(Path(__file__)),
    }
    write_json(
        out / "design.json",
        {
            "modes": MODES,
            "nominal_weights": {"D": 35, "C1": 30, "S": 15, "C4": 10},
            "nominal_total": 90,
            "quarters": QUARTERS,
            "same_area_sets_required": True,
            "separate_age_and_time_marginals_not_joint_counts": True,
            "floating_age_is_not_resident_or_worker_growth": True,
            "C1_S_C4_rules_unchanged": True,
            "data_versions": versions,
            "source_sha256": hashes,
            "new_independent_validation": False,
            "facility_time_mismatch": True,
            "base_recipes_have_seen_cohort": True,
            "operating_applied": False,
            "LLM_calls": 0,
            "additional_map_calls": 0,
        },
    )
    orders = {}
    checks = Counter()
    for index, case in enumerate(cases, 1):
        key = case["id"]
        saved = json.loads((source / "scores" / f"{key}.json").read_text(encoding="utf-8"))
        original = json.loads((historical / "scores" / f"{key}.json").read_text(encoding="utf-8"))
        main_codes = [
            a.trdar_cd
            for a, _ in overlapping_areas(
                areas, *to_epsg5181(case["site"]["latitude"], case["site"]["longitude"]), 500
            )
        ]
        evidence = {
            code: segment_changes(profile, main_codes, panels) for code, profile in catalog.items()
        }
        observed = original["data"]["floating_population"]["trend"]["yoy_change"]
        total = evidence[next(iter(INDUSTRIES))]["total"]
        if not total["available"] or total["yoy"] != observed:
            raise ValueError("기존 공통 D4 증감이 정확히 재현되어야 합니다.")
        checks["exact_original_yoy_sites"] += 1
        for feature in saved["source_features"].values():
            if feature["original_status"]["D4"] == "observed" and not math.isclose(
                d4_fraction(observed), feature["fractions"]["D4"], abs_tol=1e-12
            ):
                raise ValueError("기존 D4 점수 곡선이 재현되어야 합니다.")
        values = {m: saved["values"][m] for m in ("retained90", "balanced90")}
        details = {}
        for mode in MODES:
            scored = {}
            changes = {}
            for code, feature in saved["source_features"].items():
                fractions = dict(feature["fractions"])
                change = replacement(evidence[code], mode)
                if change["applied"] and feature["original_status"]["D4"] == "observed":
                    if change["change"] != observed:
                        fractions["D4"] = change["fraction"]
                    checks["changed_D4_features"] += fractions["D4"] != feature["fractions"]["D4"]
                changes[code] = change
                scored[code] = score90(
                    fractions,
                    feature["original_status"],
                    catalog[code],
                    saved["facility_components"][code],
                    CONFIG,
                )
                checks["actual90_scores"] += 1
            values[mode] = {code: v["normalized"] for code, v in scored.items()}
            if mode == "control" and values[mode] != saved["values"][CONFIG.name]:
                raise ValueError("원래90점 점수가 정확히 재현되어야 합니다.")
            details[mode] = {"score": scored, "D4_changes": changes}
        ties = {
            r["code"]: {"coverage": r["coverage"], "adjustment": r["space"]["adjustment"]}
            for r in original["scores"]
        }
        orders[key] = {m: order_scores(v, ties) for m, v in values.items()}
        write_json(
            out / "scores" / f"{key}.json",
            {
                **case,
                "values": values,
                "orders": orders[key],
                "details": details,
                "D4_source_evidence": evidence,
            },
        )
        if index % 50 == 0 or index == len(cases):
            print(json.dumps({"scored": index, "total": len(cases)}), flush=True)
    methods = ["retained90", "balanced90", *MODES]
    development = metrics_for(cases, orders, methods)
    for scope in development:
        old = previous["development"][scope][CONFIG.name]
        if any(
            development[scope]["control"][k] != old[k] for k in ("hit5_n", "hit10_n", "exposure5")
        ):
            raise ValueError("원래90점 지표가 재현되어야 합니다.")
    by_id = {c["id"]: c for c in cases}
    seen = set()
    oof_orders = {}
    fold_choices = {}
    for number, fold in sorted(spatial["folds"].items()):
        validate_split(by_id, fold)
        selected = choose([by_id[k] for k in fold["training_ids"]], orders, methods)
        fold_choices[number] = selected["method"]
        write_json(out / f"fold-{number}-selection.json", selected)
        for key in fold["held_ids"]:
            if key in seen:
                raise ValueError("중복 평가 위치입니다.")
            seen.add(key)
            oof_orders[key] = {
                ANCHOR: orders[key][ANCHOR],
                "control": orders[key]["control"],
                "OOF_D4": orders[key][selected["method"]],
            }
    if seen != set(by_id):
        raise ValueError("전체212곳이 보존되어야 합니다.")
    oof = metrics_for(cases, oof_orders, [ANCHOR, "control", "OOF_D4"])
    full = choose(cases, orders, methods)
    write_json(out / "full-development-selection.json", full)
    result = {
        "development": development,
        "OOF_selection_only": oof,
        "fold_choices": fold_choices,
        "full_selected": full["method"],
        "checks": dict(checks),
        "source_sha256": hashes,
        "nominal_total": 90,
        "C4_max": 10,
        "new_independent_validation": False,
        "facility_time_mismatch": True,
        "base_recipes_have_seen_cohort": True,
        "operating_applied": False,
        "LLM_calls": 0,
        "additional_map_calls": 0,
    }
    write_json(out / "results.json", result)
    write_json(out / "OOF-orders.json", oof_orders)
    write_json(
        out / "verification.json",
        {"passed": True, "n": len(cases), **dict(checks), "nominal_total": 90, "C4_max": 10},
    )

    def compact(groups):
        return {
            scope: {
                m: {
                    "hit5": v["hit5_n"],
                    "hit10": v["hit10_n"],
                    "never": v["exposure5"]["never_n"],
                    "max": v["exposure5"]["max_locations"],
                    "gini": v["exposure5"]["gini"],
                }
                for m, v in data.items()
            }
            for scope, data in groups.items()
        }

    return {
        "development": compact(development),
        "OOF": compact(oof),
        "fold_choices": fold_choices,
        "full_selected": full["method"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("source", "historical", "data", "splits", "out"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    with block_network():
        result = run(args.source, args.historical, args.data, args.splits, args.out)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
