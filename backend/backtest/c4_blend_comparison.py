"""C4 고정 결합의 개발 결과와 지역 분리 선택 결과를 별도로 저장합니다."""

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from app.agentic.scoring import profiles
from app.geo import haversine_m
from app.industries.catalog import INDUSTRIES, INDUSTRIES_WITHOUT_SEOUL
from backtest.c4_blend import (
    CONFIGURATIONS,
    CONTROL,
    FACILITY_POLICY,
    evaluate,
    score_blend,
    select_blend,
)
from backtest.c4_comparison import change_summary
from backtest.licensing import sha256
from backtest.offline import block_network, write_json
from backtest.weight_selection import order_scores

RECIPES = {"retained_C4": "retained_D75", "balanced_C4": "balanced57", "accuracy_C4": "accuracy64"}


def metrics_for(cases: list[dict], orders: dict, methods: list[str]) -> dict:
    return {
        scope: {method: evaluate(cases, orders, method, universe) for method in methods}
        for scope, universe in (
            ("all_212_candidates51", set(INDUSTRIES)),
            ("supported_184_candidates45", set(INDUSTRIES) - set(INDUSTRIES_WITHOUT_SEOUL)),
        )
    }


def validate_split(cases: dict, fold: dict) -> None:
    training, held = set(fold["training_ids"]), set(fold["held_ids"])
    if not training or not held or training & held or not (training | held) <= cases.keys():
        raise ValueError("공간 분리 학습·평가 위치가 비었거나 겹칩니다.")
    for key in training:
        a = cases[key]
        for other in held:
            b = cases[other]
            if (
                a["cluster"] == b["cluster"]
                or haversine_m(
                    a["site"]["latitude"],
                    a["site"]["longitude"],
                    b["site"]["latitude"],
                    b["site"]["longitude"],
                )
                <= 1000
            ):
                raise ValueError("공간 분리의 동일 상권·1km 제외가 유지되지 않았습니다.")


def run(source: Path, historical: Path, splits: Path, out: Path) -> dict:
    if out.exists():
        raise ValueError("이미 수행한 C4 결합 실험은 덮어쓰지 않습니다.")
    out.mkdir(parents=True)
    (out / "scores").mkdir()
    previous = json.loads((source / "results.json").read_text(encoding="utf-8"))
    source_cases = previous["cases"]
    spatial = json.loads(splits.read_text(encoding="utf-8"))
    if len(source_cases) != 212 or set(spatial["assignments"]) != {c["id"] for c in source_cases}:
        raise ValueError("원래 212곳과 동결한 지역 분리가 필요합니다.")
    if (
        sha256(Path("app/industries/data/industry_profile.csv"))
        != previous["source_sha256"]["profiles"]
    ):
        raise ValueError("C4 업종별 프로필이 원래 실험과 다릅니다.")
    if sha256(Path("backtest/c4_policy.py")) != previous["source_sha256"]["scorer"]:
        raise ValueError("고정할 C4 계산식이 바뀌었습니다.")
    source_hashes = {c["id"]: sha256(source / "scores" / f"{c['id']}.json") for c in source_cases}
    hashes = {
        "source": sha256(source / "results.json"),
        "historical": sha256(historical / "results.json"),
        "spatial_splits": sha256(splits),
        "scorer": sha256(Path("backtest/c4_blend.py")),
        "runner": sha256(Path(__file__)),
        "facility_policy": previous["source_sha256"]["scorer"],
    }
    write_json(
        out / "design.json",
        {
            "configurations": [asdict(c) for c in CONFIGURATIONS],
            "C4_policy_fixed": asdict(FACILITY_POLICY),
            "nominal_D_C1_S_total": 80,
            "effective_C4_max": 5,
            "normalized_max": 90,
            "combine_before_C4": True,
            "industry_specific_offsets_or_quotas": False,
            "selection": "train TOP5; no worse TOP10 and exposure in both scopes",
            "scope": "combination selection only; base recipes have seen this cohort",
            "base_recipes_previously_explored_on_same_cohort": True,
            "new_independent_validation": False,
            "facility_time_mismatch": True,
            "operating_applied": False,
            "additional_map_calls": 0,
            "LLM_calls": 0,
            "source_sha256": hashes,
            "source_case_sha256": source_hashes,
        },
    )
    catalog = profiles()
    predictions, orders, cases, checks = {}, {}, [], Counter()
    for index, old in enumerate(source_cases, 1):
        key = old["id"]
        saved = json.loads((source / "scores" / f"{key}.json").read_text(encoding="utf-8"))
        original = json.loads((historical / "scores" / f"{key}.json").read_text(encoding="utf-8"))
        common = {m: saved["values"][m + ":without_C4_80"] for m in RECIPES.values()}
        policy_name = "retained_D75:" + FACILITY_POLICY.name
        applicable = {
            c: d["applicable_weight"] - d["effective_C4_weight"]
            for c, d in saved["details"][policy_name].items()
        }
        ties = {
            r["code"]: {"coverage": r["coverage"], "adjustment": r["space"]["adjustment"]}
            for r in original["scores"]
        }
        values, details = {}, {}
        for config in CONFIGURATIONS:
            result = score_blend(common, applicable, catalog, saved["facility_components"], config)
            values[config.name] = result["values"]
            details[config.name] = {"common80": result["common80"], "C4": result["C4_details"]}
            checks["scores_including_C4"] += len(result["values"])
            if config.name in RECIPES:
                previous_name = RECIPES[config.name] + ":" + FACILITY_POLICY.name
                if result["values"] != saved["values"][previous_name]:
                    raise ValueError("지난 C4 포함 점수가 재현되지 않았습니다.")
                checks["exact_replayed_control_scores"] += len(result["values"])
        predictions[key] = values
        orders[key] = {name: order_scores(v, ties) for name, v in values.items()}
        for name, recipe in RECIPES.items():
            if orders[key][name] != saved["orders"][recipe + ":" + FACILITY_POLICY.name]:
                raise ValueError("지난 C4 포함 순위가 재현되지 않았습니다.")
            checks["exact_replayed_control_orders"] += 1
        case = {k: old[k] for k in ("id", "target", "site", "cluster")}
        cases.append(case)
        write_json(
            out / "scores" / f"{key}.json",
            {**case, "values": values, "details": details, "orders": orders[key]},
        )
        if index % 50 == 0 or index == len(source_cases):
            print(json.dumps({"scored": index, "total": len(source_cases)}), flush=True)
    fixed_methods = [c.name for c in CONFIGURATIONS]
    development = metrics_for(cases, orders, fixed_methods)
    for scope, metrics in development.items():
        for name, recipe in RECIPES.items():
            old = previous["scopes"][scope]["metrics"][recipe + ":" + FACILITY_POLICY.name]
            if any(metrics[name][k] != old[k] for k in ("n", "hit5_n", "hit10_n", "exposure5")):
                raise ValueError("지난 C4 포함 지표가 재현되지 않았습니다.")
    by_id = {c["id"]: c for c in cases}
    held_seen, fold_choices, oof_orders = set(), {}, {}
    for number, fold in sorted(spatial["folds"].items()):
        validate_split(by_id, fold)
        training = [by_id[k] for k in fold["training_ids"]]
        choice = select_blend(training, predictions, orders)
        choice["held_ids"] = fold["held_ids"]
        fold_choices[number] = choice["method"]
        write_json(out / f"fold-{number}-selection.json", choice)
        for key in fold["held_ids"]:
            if key in held_seen:
                raise ValueError("평가 위치가 둘 이상의 분할에 들어갔습니다.")
            held_seen.add(key)
            oof_orders[key] = {
                **{m: orders[key][m] for m in RECIPES},
                "OOF_C4_blend": orders[key][choice["method"]],
            }
    if held_seen != set(by_id):
        raise ValueError("원래 212곳이 모두 지역 분리 평가에 포함되어야 합니다.")
    selection = select_blend(cases, predictions, orders)
    write_json(out / "full-development-selection.json", selection)
    oof = metrics_for(cases, oof_orders, [*RECIPES, "OOF_C4_blend"])
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
        changes[scope] = {
            m: change_summary(selected, CONTROL, m) for m in fixed_methods if m != CONTROL
        }
    if any(
        sha256(source / "scores" / f"{key}.json") != value for key, value in source_hashes.items()
    ):
        raise ValueError("비교 도중 고정 입력 파일이 바뀌었습니다.")
    result = {
        "kind": "fixed_C4_convex_recipe_blend",
        "development": development,
        "OOF_combination_selection_only": oof,
        "fold_choices": fold_choices,
        "full_development_selected": selection["method"],
        "changes_vs_retained_C4": changes,
        "base_recipes_previously_explored_on_same_cohort": True,
        "facility_time_mismatch": True,
        "new_independent_validation": False,
        "operating_applied": False,
        "LLM_calls": 0,
        "additional_map_calls": 0,
        "source_sha256": hashes,
        "checks": dict(checks),
    }
    write_json(out / "results.json", result)
    write_json(out / "predictions.json", predictions)
    write_json(out / "OOF-orders.json", oof_orders)
    write_json(
        out / "verification.json",
        {
            "passed": True,
            "n": len(cases),
            **dict(checks),
            "original_sources_unchanged": True,
            "spatial_buffer_checked": True,
            "new_independent_validation": False,
        },
    )
    return {
        "development": {
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
            for scope, data in development.items()
        },
        "OOF": {
            scope: {
                m: {
                    "hit5": v["hit5_n"],
                    "hit10": v["hit10_n"],
                    "never": v["exposure5"]["never_n"],
                    "max": v["exposure5"]["max_locations"],
                }
                for m, v in data.items()
            }
            for scope, data in oof.items()
        },
        "fold_choices": fold_choices,
        "full_selected": selection["method"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--splits", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with block_network():
        result = run(args.source, args.historical, args.splits, args.out)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
