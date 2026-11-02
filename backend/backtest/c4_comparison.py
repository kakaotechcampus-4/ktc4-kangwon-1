"""동결한 세 가지 80점 계산식에 C4만 추가해 같은 위치에서 비교합니다."""

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean

from app.agentic.scoring import profiles, score_item
from app.industries.catalog import INDUSTRIES, INDUSTRIES_WITHOUT_SEOUL
from backtest.frozen_balanced import score_balanced
from backtest.frozen_quantile import score_candidate
from backtest.frozen_rank import score_saved
from backtest.licensing import sha256
from backtest.offline import block_network, write_json
from backtest.rank_experiment import interval, metric
from backtest.weight_selection import order_scores

METHODS = ("retained_D75", "balanced57", "accuracy64")
SCENARIOS = ("without_C4_80", "unqueried_C4_90", "observed_current_C4_90")


def add_c4(score80: float, applicable80: float, item: dict) -> dict:
    if (
        not math.isfinite(score80)
        or not 0 <= score80 <= 80 + 1e-9
        or not math.isfinite(applicable80)
        or not 0 < applicable80 <= 80
    ):
        raise ValueError("원래 80점과 적용 배점이 유효하지 않습니다.")
    state, point = item["status"], item["points"]
    if state not in ("observed", "unknown", "n.a."):
        raise ValueError("C4 관측 상태가 올바르지 않습니다.")
    if state == "observed":
        if type(point) not in (int, float) or not math.isfinite(point) or not 0 <= point <= 10:
            raise ValueError("C4 관측 점수는 0~10점이어야 합니다.")
    elif point is not None:
        raise ValueError("미확인·미적용 시설에 관측 점수를 넣을 수 없습니다.")
    applicable90 = applicable80 + (0 if state == "n.a." else 10)
    raw80 = score80 * applicable80 / 80
    raw90 = raw80 + (point if state == "observed" else 0)
    value = 90 * raw90 / applicable90
    return {
        "normalized": value,
        "raw_common80_points": raw80,
        "common80_applicable_weight": applicable80,
        "C4_status": state,
        "C4_observed_points": point,
        "C4_applicable_weight": 0 if state == "n.a." else 10,
        "raw_points": raw90,
        "applicable_weight": applicable90,
    }


def score_recipes(saved: dict, calibration: dict, panels: dict, background: dict) -> dict:
    retained = score_saved(saved, calibration)
    area = saved["data"]["area_selection"]["area_code"]
    balanced = score_balanced(saved, calibration, panels["areas"][area], panels["city"])
    accuracy = score_candidate(saved, calibration, background)
    return {
        "retained_D75": {
            "values": retained["values"]["fixed_C1_D75"],
            "applicable": {c: d["weighted"]["applicable"] for c, d in retained["details"].items()},
        },
        "balanced57": {
            "values": balanced["values"],
            "applicable": {c: d["D_applicable"] + 45 for c, d in balanced["details"].items()},
        },
        "accuracy64": {
            "values": accuracy["values"],
            "applicable": {c: d["applicable"] for c, d in accuracy["details"].items()},
        },
    }


def facility_summary(cases: list[dict]) -> dict:
    result = {}
    for code, profile in profiles().items():
        if not profile["required_facilities"]:
            continue
        items = [r["C4_items"][code] for r in cases]
        points = [item["points"] for item in items if item["status"] == "observed"]
        result[code] = {
            "name": INDUSTRIES[code],
            "required_facilities": profile["required_facilities"],
            "max_distance_m": float(profile["max_distance_m"]),
            "status_counts": dict(Counter(item["status"] for item in items)),
            "point_counts": dict(Counter(points)),
            "mean_observed_points": mean(points) if points else None,
            "target_cases": sum(r["target"] == code for r in cases),
            "target_observed_cases": sum(
                r["target"] == code and r["C4_items"][code]["status"] == "observed" for r in cases
            ),
        }
    return result


def change_summary(cases: list[dict], before: str, after: str) -> dict:
    gained, lost, changed = [], [], []
    for case in cases:
        old, new = case["orders"][before], case["orders"][after]
        old_rank, new_rank = old.index(case["target"]) + 1, new.index(case["target"]) + 1
        row = {
            "id": case["id"],
            "target": case["target"],
            "before_rank": old_rank,
            "after_rank": new_rank,
        }
        if old_rank > 5 >= new_rank:
            gained.append(row)
        if new_rank > 5 >= old_rank:
            lost.append(row)
        if set(old[:5]) != set(new[:5]):
            changed.append(case["id"])
    return {
        "gained_hit5": gained,
        "lost_hit5": lost,
        "changed_top5_sets_n": len(changed),
        "changed_top5_sets_ids": changed,
        "paired_cluster_hit5_interval": interval(cases, before, after, 5),
    }


def run(source: Path, facilities: Path, out: Path) -> dict:
    if (out / "results.json").exists():
        raise ValueError("이미 완료한 비교 결과는 덮어쓰지 않습니다.")
    root = Path("cache/ab-evaluation")
    source_cases = json.loads(source.read_text(encoding="utf-8"))["cases"]
    observation = json.loads(facilities.read_text(encoding="utf-8"))
    calibration_path = source.parent / "baselines.json"
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    panels_path = root / "20261030/S-source-provenance-comparison-v2/raw-panels.json"
    panels = json.loads(panels_path.read_text(encoding="utf-8"))
    background_path = root / "20261026/historical-competition-20252/samples.json"
    background = json.loads(background_path.read_text(encoding="utf-8"))
    frozen_accuracy_path = (
        root / "20261030/refined-domain-weight-validation/frozen-accuracy-candidate.json"
    )
    frozen_accuracy = json.loads(frozen_accuracy_path.read_text(encoding="utf-8"))
    if (
        sha256(background_path) != frozen_accuracy["source_sha256"]["city_samples"]
        or frozen_accuracy["cutoff"] != "20252"
    ):
        raise ValueError("고정한 과거 서울 분포의 분기·해시가 다릅니다.")
    background = {"reference_quarter": frozen_accuracy["cutoff"], "samples": background["samples"]}
    design = json.loads((out / "design.json").read_text(encoding="utf-8"))
    if sha256(source) != design["source_sha256"]["historical_results"]:
        raise ValueError("동결한 위치·정답 자료가 바뀌었습니다.")
    if set(observation["sites"]) != {c["id"] for c in source_cases} or len(source_cases) != 212:
        raise ValueError("같은 212곳 전체의 시설 관측 자료가 필요합니다.")
    if observation["llm_calls"] or observation["analysis_api_calls"]:
        raise ValueError("LLM·분석 API 호출이 없는 시설 관측만 허용합니다.")
    (out / "scores").mkdir(exist_ok=True)
    cases, score_checks, maximum_c4_points = [], 0, 0
    catalog = profiles()
    for index, case in enumerate(source_cases, 1):
        saved = json.loads(
            (source.parent / "scores" / f"{case['id']}.json").read_text(encoding="utf-8")
        )
        observed = observation["sites"][case["id"]]
        if saved["site"] != observed["site"] or saved["target"] != case["target"]:
            raise ValueError("시설 조회 위치와 원래 평가 위치·정답이 다릅니다.")
        recipes = score_recipes(saved, calibration, panels, background)
        items = {
            c: score_item("C4", catalog[c], c, {"facilities": observed["facilities"]})
            for c in INDUSTRIES
        }
        missing = {c: score_item("C4", catalog[c], c, {}) for c in INDUSTRIES}
        ties = {
            r["code"]: {"coverage": r["coverage"], "adjustment": r["space"]["adjustment"]}
            for r in saved["scores"]
        }
        if any(t["adjustment"] != 0 for t in ties.values()):
            raise ValueError("시설 외 공간 보정이 달라지지 않는 표본만 비교합니다.")
        scores, details, orders = {}, {}, {}
        for method, recipe in recipes.items():
            scores[method + ":without_C4_80"] = recipe["values"]
            for scenario, facility_items in (
                ("unqueried_C4_90", missing),
                ("observed_current_C4_90", items),
            ):
                name = method + ":" + scenario
                details[name] = {
                    c: add_c4(recipe["values"][c], recipe["applicable"][c], facility_items[c])
                    for c in INDUSTRIES
                }
                scores[name] = {c: d["normalized"] for c, d in details[name].items()}
                score_checks += len(scores[name])
            for scenario in SCENARIOS:
                name = method + ":" + scenario
                orders[name] = order_scores(scores[name], ties)
        result = {
            **{k: case[k] for k in ("id", "target", "site", "cluster")},
            "C4_items": items,
            "orders": orders,
        }
        cases.append(result)
        write_json(
            out / "scores" / f"{case['id']}.json",
            {**result, "values": scores, "score_details": details},
        )
        maximum_c4_points = max(
            maximum_c4_points, *(item["points"] or 0 for item in items.values())
        )
        if index % 40 == 0 or index == len(source_cases):
            print(json.dumps({"scored_sites": index, "total": len(source_cases)}), flush=True)
    scopes = {}
    for scope, universe in (
        ("all_212_candidates51", set(INDUSTRIES)),
        ("supported_184_candidates45", set(INDUSTRIES) - set(INDUSTRIES_WITHOUT_SEOUL)),
    ):
        selected = [
            {
                **c,
                "orders": {
                    name: [code for code in order if code in universe]
                    for name, order in c["orders"].items()
                },
            }
            for c in cases
            if c["target"] in universe
        ]
        scopes[scope] = {
            "n": len(selected),
            "candidate_n": len(universe),
            "metrics": {name: metric(selected, name, universe) for name in selected[0]["orders"]},
            "paired_changes": {
                m: change_summary(selected, m + ":without_C4_80", m + ":observed_current_C4_90")
                for m in METHODS
            },
        }
    controls = {}
    for method in METHODS:
        primary = scopes["all_212_candidates51"]["metrics"][method + ":without_C4_80"]
        supported = scopes["supported_184_candidates45"]["metrics"][method + ":without_C4_80"]
        controls[method] = [
            primary["hit5_n"],
            supported["hit5_n"],
            primary["hit10_n"],
            supported["hit10_n"],
        ]
    if controls != design["expected_controls"]:
        raise ValueError(f"C4 추가 전 결과가 재현되지 않았습니다: {controls}")
    result = {
        "kind": "C4_addition_with_current_facilities_historical_other_inputs",
        "scopes": scopes,
        "facility_coverage": facility_summary(cases),
        "cases": cases,
        "facility_time_mismatch": True,
        "pure_historical_backtest": False,
        "new_independent_validation": False,
        "operating_applied": False,
        "tie_metadata_frozen_from_original": True,
        "LLM_calls": 0,
        "analysis_api_calls": 0,
        "scoring_external_http_requests": 0,
        "facility_query_unique_requests": observation["unique_requests"],
        "provenance": {
            "source": sha256(source),
            "facilities": sha256(facilities),
            "calibration": sha256(calibration_path),
            "raw_panels": sha256(panels_path),
            "background": sha256(background_path),
            "design": sha256(out / "design.json"),
        },
        "limits": [
            "시설만 현재 조회 자료이며 2025Q2 존재 여부를 입증하지 않습니다.",
            "기존 개발 표본의 재평가로 새 지역 독립 검증이 아닙니다.",
            "검색 0건·누락 거리는 미확인이며 시설 부재나 관측 0점으로 바꾸지 않습니다.",
            "미적용 업종은 C4 배점을 분모에서 제외하고 90점으로 환산합니다.",
            "기존 관측률·공간 보정 동점 규칙은 고정해 시설 점수의 영향만 비교합니다.",
        ],
    }
    write_json(out / "results.json", result)
    write_json(
        out / "verification.json",
        {
            "passed": True,
            "paired_n": len(cases),
            "controls_replayed": controls,
            "C4_90_score_checks": score_checks,
            "maximum_C4_points": maximum_c4_points,
            "scoring_network_blocked": True,
            "llm_calls": 0,
        },
    )
    return {
        "controls": controls,
        "scopes": {
            scope: {
                name: {key: value[key] for key in ("hit5_n", "hit10_n", "mean_target_rank")}
                for name, value in data["metrics"].items()
            }
            for scope, data in scopes.items()
        },
        "facility_coverage": result["facility_coverage"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--facilities", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with block_network():
        result = run(args.source, args.facilities, args.out)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
