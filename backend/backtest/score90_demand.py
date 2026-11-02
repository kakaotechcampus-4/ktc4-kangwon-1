"""과거 유동인구를 일치시킨 C1 백분위를 C4 포함90점에서 비교합니다."""

import argparse
import json
from collections import Counter
from pathlib import Path

from app.agentic.scoring import profiles
from app.agents.floating_population.models import FlpopRecord, TrdarArea
from app.db.connection import readonly
from app.geo import haversine_m
from backtest.c4_blend_comparison import metrics_for, validate_split
from backtest.competition_demand import MODES, competition_fraction, matching_daily
from backtest.licensing import sha256
from backtest.offline import block_network, write_json
from backtest.score90 import Score90Configuration, score90
from backtest.score90_comparison import ANCHOR, choose
from backtest.weight_selection import order_scores

CONFIG = Score90Configuration(30, "equal")


def load_population(data: Path):
    with readonly(data) as db:
        versions = {}
        for source in ("floating", "areas"):
            rows = db.execute(
                "SELECT v.*,f.columns_json FROM data_versions v "
                "JOIN source_fields f USING(version_id) "
                "WHERE v.source=? AND v.state='active'"
                + (" AND v.quarter='20252'" if source == "floating" else ""),
                (source,),
            ).fetchall()
            if len(rows) != 1:
                raise ValueError("고정 분기의 유동인구와 상권영역 자료 버전이 하나씩 필요합니다.")
            versions[source] = dict(rows[0])

        def read(source):
            version = versions[source]
            columns = json.loads(version["columns_json"])
            return [
                dict(zip(columns, json.loads(row[0]), strict=True))
                for row in db.execute(
                    f"SELECT payload FROM {source} WHERE version_id=?", (version["version_id"],)
                )
            ]

        records = [FlpopRecord.from_api_row(row) for row in read("floating")]
        areas = []
        for original in read("areas"):
            row = dict(original)
            for source, target in (
                ("XCNTS_VALU", "XCNTS_VALUE"),
                ("YDNTS_VALU", "YDNTS_VALUE"),
                ("TRDAR_CD_N", "TRDAR_CD_NM"),
            ):
                row[target] = row.get(target, row.get(source))
            areas.append(TrdarArea.from_api_row(row))
    if {r.stdr_yyqu_cd for r in records} != {"20252"} or len(records) != len(
        {r.trdar_cd for r in records}
    ):
        raise ValueError("같은 분기의 중복 없는 유동인구만 사용합니다.")
    return areas, {r.trdar_cd: r.total for r in records}, versions


def run(source, historical, background, data, splits, out):
    if out.exists():
        raise ValueError("기존 수요 보정 실험은 덮어쓰지 않습니다.")
    out.mkdir(parents=True)
    (out / "scores").mkdir()
    previous = json.loads((source / "results.json").read_text(encoding="utf-8"))
    historical_results = json.loads((historical / "results.json").read_text(encoding="utf-8"))
    cases = [
        {k: c[k] for k in ("id", "target", "site", "cluster")} for c in historical_results["cases"]
    ]
    city = json.loads(background.read_text(encoding="utf-8"))["samples"]
    spatial = json.loads(splits.read_text(encoding="utf-8"))
    if (
        len(cases) != 212
        or len(city) != 1650
        or set(spatial["assignments"]) != {c["id"] for c in cases}
    ):
        raise ValueError("원래 212곳·서울 참고 분포·지역 분리가 필요합니다.")
    areas, totals, versions = load_population(data)
    hashes = {
        "source": sha256(source / "results.json"),
        "historical": sha256(historical / "results.json"),
        "background": sha256(background),
        "splits": sha256(splits),
        "scorer": sha256(Path("backtest/competition_demand.py")),
        "runner": sha256(Path(__file__)),
    }
    write_json(
        out / "design.json",
        {
            "modes": MODES,
            "D": 35,
            "C1": 30,
            "S": 15,
            "C4": 10,
            "nominal_total": 90,
            "C1_percentile_fraction": 0.5,
            "C1_LQ_fraction": 0.5,
            "matching_population": "same500m overlap and mean_daily_per_trade_area, 20252",
            "data_versions": versions,
            "source_sha256": hashes,
            "new_independent_validation": False,
            "base_recipes_have_seen_cohort": True,
            "facility_time_mismatch": True,
            "operating_applied": False,
            "LLM_calls": 0,
            "additional_map_calls": 0,
        },
    )
    city_demand = {r["area"]: matching_daily(r, areas, totals) for r in city}
    write_json(out / "city-demand.json", city_demand)
    catalog = profiles()
    orders = {}
    checks = Counter()
    for index, case in enumerate(cases, 1):
        key = case["id"]
        saved = json.loads((source / "scores" / f"{key}.json").read_text(encoding="utf-8"))
        original = json.loads((historical / "scores" / f"{key}.json").read_text(encoding="utf-8"))
        actual = original["data"]["floating_population"]["benchmark"]["mean_daily_per_trade_area"]
        replay = matching_daily(case["site"], areas, totals)
        if replay["daily"] != actual:
            raise ValueError("현재·과거 평균 혼입 없이 원래 유동인구가 재현되어야 합니다.")
        checks["exact_population_replay_sites"] += 1
        area = original["data"]["area_selection"]["area_code"]
        reference = [
            r
            for r in city
            if r["area"] != area
            and haversine_m(
                case["site"]["latitude"], case["site"]["longitude"], r["latitude"], r["longitude"]
            )
            > 1000
        ]
        commercial = {r["code"]: r for r in original["data"]["commercial_area"]["by_middle"]}
        originals = {r["code"]: r for r in original["scores"]}
        values = {m: saved["values"][m] for m in ("retained90", "balanced90")}
        details = {}
        for mode in MODES:
            detail = {}
            evidence = {}
            for code, features in saved["source_features"].items():
                fractions = dict(features["fractions"])
                item = originals[code]["items"]["C1"]
                if (
                    item["status"] == "observed"
                    and item.get("value") is not None
                    and commercial[code].get("lq") is not None
                ):
                    refs = [(r["counts"][code], city_demand[r["area"]]["daily"]) for r in reference]
                    baseline = competition_fraction(
                        commercial[code]["count"], actual, refs, item["agglomeration"], "count"
                    )
                    changed = competition_fraction(
                        commercial[code]["count"], actual, refs, item["agglomeration"], mode
                    )
                    if changed["available"]:
                        delta = 0.5 * (changed["profile_fraction"] - baseline["profile_fraction"])
                        fractions["C1"] += delta
                        evidence[code] = {
                            "before": baseline,
                            "after": changed,
                            "C1_fraction_delta": delta,
                        }
                detail[code] = score90(
                    fractions,
                    features["original_status"],
                    catalog[code],
                    saved["facility_components"][code],
                    CONFIG,
                )
                checks["actual90_scores"] += 1
            values[mode] = {code: v["normalized"] for code, v in detail.items()}
            if mode == "count" and values[mode] != saved["values"][CONFIG.name]:
                raise ValueError("기존 실제90점 기준을 정확히 재현해야 합니다.")
            details[mode] = {"score": detail, "C1_demand_evidence": evidence}
        ties = {
            code: {"coverage": row["coverage"], "adjustment": row["space"]["adjustment"]}
            for code, row in originals.items()
        }
        orders[key] = {m: order_scores(v, ties) for m, v in values.items()}
        write_json(
            out / "scores" / f"{key}.json",
            {
                **case,
                "values": values,
                "orders": orders[key],
                "details": details,
                "population_replay": replay,
            },
        )
        if index % 50 == 0 or index == len(cases):
            print(json.dumps({"scored": index, "total": len(cases)}), flush=True)
    methods = ["retained90", "balanced90", *MODES]
    development = metrics_for(cases, orders, methods)
    for scope in development:
        old = previous["development"][scope][CONFIG.name]
        if any(
            development[scope]["count"][k] != old[k] for k in ("hit5_n", "hit10_n", "exposure5")
        ):
            raise ValueError("기존90점 적중과 추천 분포가 재현되어야 합니다.")
    by_id = {c["id"]: c for c in cases}
    oof_orders = {}
    seen = set()
    fold_choices = {}
    for number, fold in sorted(spatial["folds"].items()):
        validate_split(by_id, fold)
        choice = choose([by_id[k] for k in fold["training_ids"]], orders, methods)
        fold_choices[number] = choice["method"]
        write_json(out / f"fold-{number}-selection.json", choice)
        for key in fold["held_ids"]:
            if key in seen:
                raise ValueError("중복 평가 위치입니다.")
            seen.add(key)
            oof_orders[key] = {
                ANCHOR: orders[key][ANCHOR],
                "count": orders[key]["count"],
                "OOF_demand90": orders[key][choice["method"]],
            }
    if seen != set(by_id):
        raise ValueError("전체 위치가 보존되어야 합니다.")
    oof = metrics_for(cases, oof_orders, [ANCHOR, "count", "OOF_demand90"])
    full = choose(cases, orders, methods)
    write_json(out / "full-development-selection.json", full)
    result = {
        "development": development,
        "OOF_selection_only": oof,
        "fold_choices": fold_choices,
        "full_selected": full["method"],
        "checks": dict(checks),
        "source_sha256": hashes,
        "C4_max_points": 10,
        "nominal_score_max": 90,
        "facility_time_mismatch": True,
        "base_recipes_have_seen_cohort": True,
        "new_independent_validation": False,
        "operating_applied": False,
        "LLM_calls": 0,
        "additional_map_calls": 0,
    }
    write_json(out / "results.json", result)
    write_json(out / "OOF-orders.json", oof_orders)
    write_json(
        out / "verification.json",
        {
            "passed": True,
            "n": len(cases),
            **dict(checks),
            "nominal_score_max": 90,
            "C4_max_points": 10,
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
        "development": compact(development),
        "OOF": compact(oof),
        "fold_choices": fold_choices,
        "full_selected": full["method"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("source", "historical", "background", "data", "splits", "out"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    with block_network():
        result = run(
            args.source, args.historical, args.background, args.data, args.splits, args.out
        )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
