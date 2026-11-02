"""C4 10점을 고정하고 S의 항목별 비중을 실제90점에서 비교합니다."""

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from app.agentic.scoring import profiles
from app.industries.catalog import INDUSTRIES, INDUSTRIES_WITHOUT_SEOUL
from backtest.c4_blend import evaluate, no_worse
from backtest.c4_blend_comparison import metrics_for, validate_split
from backtest.c4_comparison import change_summary
from backtest.frozen_quantile import score_candidate
from backtest.licensing import sha256
from backtest.offline import block_network, write_json
from backtest.s4_difference import changed_fraction, difference_evidence
from backtest.score90 import C4_POLICY, CONFIGURATIONS, CONTROL, S_RATIOS, score90
from backtest.weight_selection import order_scores

ANCHOR = "retained90"
REFERENCES = {"retained90": "retained_D75", "balanced90": "balanced57"}


def choose(training: list[dict], orders: dict, methods: list[str]) -> dict:
    if not training or len({c["id"] for c in training}) != len(training):
        raise ValueError("중복 없는 학습 위치가 필요합니다.")
    stats = {
        m: {
            "primary": evaluate(training, orders, m, set(INDUSTRIES)),
            "supported": evaluate(
                training, orders, m, set(INDUSTRIES) - set(INDUSTRIES_WITHOUT_SEOUL)
            ),
        }
        for m in methods
    }
    eligible = [
        m
        for m in methods
        if all(no_worse(stats[m][s], stats[ANCHOR][s]) for s in ("primary", "supported"))
    ]
    winner = min(
        eligible,
        key=lambda m: (
            -stats[m]["primary"]["hit5_n"],
            -stats[m]["supported"]["hit5_n"],
            -stats[m]["primary"]["hit10_n"],
            stats[m]["primary"]["exposure5"]["gini"],
            m != ANCHOR,
            m,
        ),
    )
    return {
        "method": winner,
        "training_ids": sorted(c["id"] for c in training),
        "eligible_methods": eligible,
        "candidates": stats,
        "held_labels_used_for_selection": False,
    }


def run(
    source: Path, historical: Path, background: Path, panels: Path, splits: Path, out: Path
) -> dict:
    if out.exists():
        raise ValueError("완료한 90점 실험은 덮어쓰지 않습니다.")
    out.mkdir(parents=True)
    (out / "scores").mkdir()
    previous = json.loads((source / "results.json").read_text(encoding="utf-8"))
    cases = [{k: c[k] for k in ("id", "target", "site", "cluster")} for c in previous["cases"]]
    city = json.loads(background.read_text(encoding="utf-8"))["samples"]
    raw = json.loads(panels.read_text(encoding="utf-8"))
    calibration = json.loads((historical / "baselines.json").read_text(encoding="utf-8"))
    spatial = json.loads(splits.read_text(encoding="utf-8"))
    if (
        len(cases) != 212
        or len(city) != 1650
        or {r["reference_quarter"] for r in city} != {"20252"}
        or set(spatial["assignments"]) != {c["id"] for c in cases}
    ):
        raise ValueError("같은 212곳·과거 참고 분포·지역 분리가 필요합니다.")
    if C4_POLICY.low_confidence_scale != 1:
        raise ValueError("이번 비교는 C4 10점을 유지해야 합니다.")
    catalog = profiles()
    if (
        sha256(Path("backtest/c4_policy.py")) != previous["source_sha256"]["scorer"]
        or sha256(Path("app/industries/data/industry_profile.csv"))
        != previous["source_sha256"]["profiles"]
    ):
        raise ValueError("동결한 시설 계산·프로필과 같아야 합니다.")
    hashes = {
        "source": sha256(source / "results.json"),
        "historical": sha256(historical / "results.json"),
        "background": sha256(background),
        "panels": sha256(panels),
        "splits": sha256(splits),
        "scorer": sha256(Path("backtest/score90.py")),
        "runner": sha256(Path(__file__)),
    }
    write_json(
        out / "design.json",
        {
            "configurations": [
                {**asdict(c), "name": c.name, "item_weights": c.weights} for c in CONFIGURATIONS
            ],
            "survival_ratios": S_RATIOS,
            "nominal_common_points": 80,
            "C4_max_points": 10,
            "nominal_score_max": 90,
            "not_85_rescaled_to_90": True,
            "C4_policy": asdict(C4_POLICY),
            "D_weight": 35,
            "missing_statuses_and_penalties_preserved": True,
            "S4_repair": "complete source; old closures=0; both windows exposure>=40",
            "selection": "training TOP5 with no worse TOP10 and exposure in both scopes",
            "new_independent_validation": False,
            "base_recipes_have_seen_cohort": True,
            "facility_time_mismatch": True,
            "operating_applied": False,
            "source_sha256": hashes,
            "LLM_calls": 0,
            "additional_map_calls": 0,
        },
    )
    orders, checks, feature_hashes = {}, Counter(), {}
    for index, case in enumerate(cases, 1):
        key = case["id"]
        original = json.loads((historical / "scores" / f"{key}.json").read_text(encoding="utf-8"))
        saved = json.loads((source / "scores" / f"{key}.json").read_text(encoding="utf-8"))
        if original["site"] != saved["site"] or original["target"] != case["target"]:
            raise ValueError("원래 위치와 실제 업종이 같아야 합니다.")
        base = score_candidate(
            original, calibration, {"reference_quarter": "20252", "samples": city}
        )
        area = original["data"]["area_selection"]["area_code"]
        repairs, repair_evidence = {}, {}
        partial = "business_lifecycle" in original["data"]["runtime_partial_sources"]
        for code in INDUSTRIES:
            evidence = (
                {"available": False, "reason": "partial_source"}
                if partial
                else difference_evidence(code, raw["quarters"], raw["areas"][area], raw["city"])
            )
            repair = changed_fraction(
                base["details"][code]["original_status"]["S4"], evidence, "zero_old_only"
            )
            repairs[code] = repair
            if repair is not None:
                repair_evidence[code] = evidence
                checks["source_verified_S4_repairs"] += 1
        ties = {
            r["code"]: {"coverage": r["coverage"], "adjustment": r["space"]["adjustment"]}
            for r in original["scores"]
        }
        values = {
            m: saved["values"][recipe + ":" + C4_POLICY.name] for m, recipe in REFERENCES.items()
        }
        details = {}
        for config in CONFIGURATIONS:
            details[config.name] = {
                code: score90(
                    base["details"][code]["fractions"],
                    base["details"][code]["original_status"],
                    catalog[code],
                    saved["facility_components"][code],
                    config,
                    S4_repair=repairs[code],
                )
                for code in INDUSTRIES
            }
            values[config.name] = {c: d["normalized"] for c, d in details[config.name].items()}
            if config.name == CONTROL:
                old_values = saved["values"]["accuracy64:" + C4_POLICY.name]
                if values[config.name] != old_values:
                    raise ValueError("기존 실제90점 정확도 기준이 정확히 재현되지 않았습니다.")
                checks["exact_replayed_control_scores"] += len(old_values)
            checks["true90_scores_checked"] += len(values[config.name])
        orders[key] = {m: order_scores(v, ties) for m, v in values.items()}
        if orders[key][CONTROL] != saved["orders"]["accuracy64:" + C4_POLICY.name]:
            raise ValueError("기존 실제90점 순위가 재현되어야 합니다.")
        write_json(
            out / "scores" / f"{key}.json",
            {
                **case,
                "values": values,
                "orders": orders[key],
                "details": details,
                "source_features": base["details"],
                "S4_repair_evidence": repair_evidence,
                "facility_components": saved["facility_components"],
            },
        )
        feature_hashes[key] = sha256(out / "scores" / f"{key}.json")
        if index % 40 == 0 or index == len(cases):
            print(
                json.dumps(
                    {"scored": index, "total": len(cases), "configurations": len(CONFIGURATIONS)}
                ),
                flush=True,
            )
    methods = [*REFERENCES, *(c.name for c in CONFIGURATIONS)]
    development = metrics_for(cases, orders, methods)
    expected = {"all_212_candidates51": (65, 86), "supported_184_candidates45": (66, 88)}
    for scope, (hit5, hit10) in expected.items():
        m = development[scope][CONTROL]
        if (m["hit5_n"], m["hit10_n"]) != (hit5, hit10):
            raise ValueError("고정한 실제90점 지표와 달라졌습니다.")
    by_id = {c["id"]: c for c in cases}
    oof_orders, seen, fold_choices = {}, set(), {}
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
                CONTROL: orders[key][CONTROL],
                "OOF_true90": orders[key][choice["method"]],
            }
    if seen != set(by_id):
        raise ValueError("전체 212곳이 평가되어야 합니다.")
    oof = metrics_for(cases, oof_orders, [ANCHOR, CONTROL, "OOF_true90"])
    full = choose(cases, orders, methods)
    write_json(out / "full-development-selection.json", full)
    primary = development["all_212_candidates51"]
    best = min(
        (c.name for c in CONFIGURATIONS),
        key=lambda m: (
            -primary[m]["hit5_n"],
            primary[m]["exposure5"]["never_n"],
            primary[m]["exposure5"]["max_locations"],
            primary[m]["exposure5"]["gini"],
            m,
        ),
    )
    changes = {}
    for scope, universe in (
        ("all_212_candidates51", set(INDUSTRIES)),
        ("supported_184_candidates45", set(INDUSTRIES) - set(INDUSTRIES_WITHOUT_SEOUL)),
    ):
        selected = [
            {
                **c,
                "orders": {
                    m: [code for code in order if code in universe]
                    for m, order in orders[c["id"]].items()
                },
            }
            for c in cases
            if c["target"] in universe
        ]
        changes[scope] = change_summary(selected, CONTROL, best)
    result = {
        "development": development,
        "OOF_selection_only": oof,
        "best_development_accuracy": best,
        "full_selected_with_spread_constraints": full["method"],
        "fold_choices": fold_choices,
        "changes_best_vs_control": changes,
        "checks": dict(checks),
        "source_sha256": hashes,
        "case_sha256": feature_hashes,
        "nominal_score_max": 90,
        "C4_max_points": 10,
        "not_85_rescaled_to_90": True,
        "facility_time_mismatch": True,
        "new_independent_validation": False,
        "base_recipes_have_seen_cohort": True,
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
            "C4_max_points": 10,
            "nominal_score_max": 90,
            "new_independent_validation": False,
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
        "best_development": best,
        "full_selected": full["method"],
        "fold_choices": fold_choices,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("source", "historical", "background", "panels", "splits", "out"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    with block_network():
        result = run(
            args.source, args.historical, args.background, args.panels, args.splits, args.out
        )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
