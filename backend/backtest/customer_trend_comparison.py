"""실제 과거 상주·직장·유동의 같은 연령 모집단으로 D4를90점에서 비교합니다."""

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from app.agentic.scoring import profiles
from app.agents.floating_population.geo import overlapping_areas
from app.agents.floating_population.models import PopulationRecord
from app.agents.floating_population.numeric import complete_sum
from app.db.connection import readonly
from app.geo import to_epsg5181
from backtest.c4_blend_comparison import metrics_for, validate_split
from backtest.customer_trend import MODES, evidence_for, relative_change
from backtest.demand_trend import d4_fraction
from backtest.demand_trend_comparison import load_history
from backtest.licensing import sha256
from backtest.offline import block_network, write_json
from backtest.past_data import public_rows
from backtest.score90 import Score90Configuration, score90
from backtest.score90_comparison import ANCHOR, choose
from backtest.weight_selection import order_scores

CONFIG = Score90Configuration(30, "equal")
KINDS = {"resident": ("상주", "REPOP"), "worker": ("직장", "WRC_POPLTN")}


def customer_panels(data, downloads):
    areas, floating, metadata = load_history(data)
    panels = {"유동": floating}
    sources = {"floating": metadata}
    with readonly(data) as db:
        for source, (population, kind) in KINDS.items():
            versions = db.execute(
                "SELECT v.*,f.columns_json FROM data_versions v "
                "JOIN source_fields f USING(version_id) "
                "WHERE v.source=? AND v.quarter='20252' AND v.state='active'",
                (source,),
            ).fetchall()
            if len(versions) != 1:
                raise ValueError("현재 분기의 고정 모집단 버전이 하나씩 필요합니다.")
            version = dict(versions[0])
            columns = json.loads(version["columns_json"])
            current = [
                PopulationRecord.from_api_row(
                    dict(zip(columns, json.loads(r[0]), strict=True)), kind
                )
                for r in db.execute(
                    f"SELECT payload FROM {source} WHERE version_id=?", (version["version_id"],)
                )
            ]
            old = [
                PopulationRecord.from_api_row(r, kind)
                for r in public_rows(downloads, source, "20242")
            ]
            if len(old) != len({r.trdar_cd for r in old}) or {r.stdr_yyqu_cd for r in old} != {
                "20242"
            }:
                raise ValueError("전년 자료의 분기·자연키가 유효해야 합니다.")
            panels[population] = {
                "20242": {r.trdar_cd: r for r in old},
                "20252": {r.trdar_cd: r for r in current},
            }
            sources[source] = {
                "current_version": version,
                "old_sha256": sha256(downloads / f"{source}-20242.json"),
                "old_n": len(old),
                "current_n": len(current),
            }
    return areas, panels, sources


def run(source, historical, data, downloads, splits, out):
    if out.exists():
        raise ValueError("기존 실제 고객층 실험은 덮어쓰지 않습니다.")
    out.mkdir(parents=True)
    (out / "scores").mkdir()
    previous = json.loads((source / "results.json").read_text(encoding="utf-8"))
    reference = json.loads((historical / "results.json").read_text(encoding="utf-8"))
    cases = [{k: c[k] for k in ("id", "target", "site", "cluster")} for c in reference["cases"]]
    spatial = json.loads(splits.read_text(encoding="utf-8"))
    catalog = profiles()
    if len(cases) != 212 or set(spatial["assignments"]) != {c["id"] for c in cases}:
        raise ValueError("같은212곳의 지역 분리가 필요합니다.")
    areas, panels, sources = customer_panels(data, downloads)
    hashes = {
        "source": sha256(source / "results.json"),
        "historical": sha256(historical / "results.json"),
        "splits": sha256(splits),
        "scorer": sha256(Path("backtest/customer_trend.py")),
        "runner": sha256(Path(__file__)),
    }
    write_json(
        out / "design.json",
        {
            "modes": MODES,
            "nominal_weights": {"D": 35, "C1": 30, "S": 15, "C4": 10},
            "nominal_total": 90,
            "same_population_and_local_area_sets_required": True,
            "stocks_not_divided_by_days": True,
            "city_reference_explicit_common_area_basis": True,
            "resident_stock_is_annual_updated_not_independent_quarterly_samples": True,
            "source_metadata": sources,
            "source_sha256": hashes,
            "new_independent_validation": False,
            "base_recipes_have_seen_cohort": True,
            "facility_time_mismatch": True,
            "operating_applied": False,
            "LLM_calls": 0,
            "map_calls": 0,
            "public_files_downloaded_prior_to_scoring": 2,
        },
    )
    orders = {}
    city_cache = {}
    checks = Counter()
    for index, case in enumerate(cases, 1):
        key = case["id"]
        saved = json.loads((source / "scores" / f"{key}.json").read_text(encoding="utf-8"))
        original = json.loads((historical / "scores" / f"{key}.json").read_text(encoding="utf-8"))
        codes = [
            a.trdar_cd
            for a, _ in overlapping_areas(
                areas, *to_epsg5181(case["site"]["latitude"], case["site"]["longitude"]), 500
            )
        ]
        for source_name, (population, _) in KINDS.items():
            block = original["data"]["floating_population"].get(source_name)
            local = [r for code, r in panels[population]["20252"].items() if code in codes]
            if block is not None and (
                complete_sum(r.total for r in local) != block["count"]
                or len(local) != block["covered_trade_areas"]
            ):
                raise ValueError("기존 D3와 현재 고객 모집단의 범위·인원수가 같아야 합니다.")
            checks["current_population_block_replays"] += block is not None
        evidence = {
            code: evidence_for(profile, codes, panels, city_cache)
            for code, profile in catalog.items()
        }
        checks["available_matched_customer_segments"] += sum(
            e["available"] for e in evidence.values()
        )
        values = {m: saved["values"][m] for m in ("retained90", "balanced90")}
        details = {}
        for mode in MODES:
            scored = {}
            changes = {}
            for code, feature in saved["source_features"].items():
                fractions = dict(feature["fractions"])
                e = evidence[code]
                changed = False
                if (
                    mode != "control"
                    and e["available"]
                    and feature["original_status"]["D4"] == "observed"
                ):
                    rate = relative_change(e) if mode == "customer_relative" else e["local"]["yoy"]
                    if rate is not None:
                        new = d4_fraction(rate)
                        if mode == "customer_half":
                            new = (new + fractions["D4"]) / 2
                        if not math.isclose(new, fractions["D4"], abs_tol=1e-12):
                            fractions["D4"] = new
                            changed = True
                changes[code] = changed
                scored[code] = score90(
                    fractions,
                    feature["original_status"],
                    catalog[code],
                    saved["facility_components"][code],
                    CONFIG,
                )
                checks["actual90_scores"] += 1
            values[mode] = {c: v["normalized"] for c, v in scored.items()}
            if mode == "control" and values[mode] != saved["values"][CONFIG.name]:
                raise ValueError("원래90점 기준이 정확히 재현되어야 합니다.")
            details[mode] = {"score": scored, "D4_changed": changes}
        ties = {
            r["code"]: {"coverage": r["coverage"], "adjustment": r["space"]["adjustment"]}
            for r in original["scores"]
        }
        orders[key] = {m: order_scores(v, ties) for m, v in values.items()}
        compact_evidence = {}
        for code, e in evidence.items():
            if not e["available"]:
                compact_evidence[code] = e
                continue
            city = e["city_matched_area_reference"]
            compact_evidence[code] = {
                **e,
                "city_reference_id": "|".join([e["population"], *e["local"]["age_bands"]]),
                "city_matched_area_reference": {k: v for k, v in city.items() if k != "area_codes"},
                "city_area_n": len(city.get("area_codes", [])),
            }
        write_json(
            out / "scores" / f"{key}.json",
            {
                **case,
                "values": values,
                "orders": orders[key],
                "details": details,
                "customer_source_evidence": compact_evidence,
            },
        )
        if index % 50 == 0 or index == len(cases):
            print(json.dumps({"scored": index, "total": len(cases)}), flush=True)
    write_json(
        out / "city-age-reference.json",
        {"|".join([kind, *ages]): value for (kind, ages), value in city_cache.items()},
    )
    methods = ["retained90", "balanced90", *MODES]
    metrics = metrics_for(cases, orders, methods)
    for scope in metrics:
        old = previous["development"][scope][CONFIG.name]
        if any(metrics[scope]["control"][k] != old[k] for k in ("hit5_n", "hit10_n", "exposure5")):
            raise ValueError("기준90점 지표가 정확히 재현되어야 합니다.")
    by_id = {c["id"]: c for c in cases}
    seen = set()
    oof_orders = {}
    fold_choices = {}
    for number, fold in sorted(spatial["folds"].items()):
        validate_split(by_id, fold)
        choice = choose([by_id[k] for k in fold["training_ids"]], orders, methods)
        fold_choices[number] = choice["method"]
        write_json(out / f"fold-{number}-selection.json", choice)
        for key in fold["held_ids"]:
            if key in seen:
                raise ValueError("평가 위치가 중복되었습니다.")
            seen.add(key)
            oof_orders[key] = {
                ANCHOR: orders[key][ANCHOR],
                "control": orders[key]["control"],
                "OOF_customer": orders[key][choice["method"]],
            }
    if seen != set(by_id):
        raise ValueError("원래212곳이 보존되어야 합니다.")
    oof = metrics_for(cases, oof_orders, [ANCHOR, "control", "OOF_customer"])
    full = choose(cases, orders, methods)
    write_json(out / "full-development-selection.json", full)
    result = {
        "development": metrics,
        "OOF_selection_only": oof,
        "fold_choices": fold_choices,
        "full_selected": full["method"],
        "checks": dict(checks),
        "source_sha256": hashes,
        "nominal_total": 90,
        "C4_max": 10,
        "new_independent_validation": False,
        "base_recipes_have_seen_cohort": True,
        "facility_time_mismatch": True,
        "operating_applied": False,
        "LLM_calls": 0,
        "map_calls": 0,
        "public_file_downloads": 2,
    }
    write_json(out / "results.json", result)
    write_json(out / "OOF-orders.json", oof_orders)
    write_json(
        out / "verification.json",
        {
            "passed": True,
            "n": len(cases),
            **dict(checks),
            "source_population_matched": True,
            "nominal_total": 90,
            "C4_max": 10,
        },
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
        "development": compact(metrics),
        "OOF": compact(oof),
        "fold_choices": fold_choices,
        "full_selected": full["method"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("source", "historical", "data", "downloads", "splits", "out"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    with block_network():
        result = run(args.source, args.historical, args.data, args.downloads, args.splits, args.out)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
