"""과거 입력을 고정하고 추천 쏠림·TOP5/TOP10을 같은 조건으로 비교합니다."""

import argparse
import copy
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean

from app.industries.catalog import INDUSTRIES, INDUSTRIES_WITHOUT_SEOUL
from backtest.ab_metrics import paired_cluster_interval, rank_of, summarize
from backtest.followup import C_ITEMS
from backtest.licensing import sha256
from backtest.offline import block_network, write_json
from backtest.past80 import csv_file
from backtest.rank_calibration import (
    CALIBRATIONS,
    EXCLUSION_RADIUS_M,
    MIN_REFERENCE_CLUSTERS,
    apply_calibration,
    reference_for,
)
from backtest.rank_demand import DEMAND_VARIANTS, apply_demand
from backtest.rank_market import MARKET_VARIANTS, apply_market
from backtest.rank_variant import (
    ALL_VARIANTS,
    C1_VARIANTS,
    Variant,
    describe,
    order_rows,
    score_row,
)

CALIBRATION_VARIANTS = (
    Variant("current"),
    Variant("current_s_ratio", s_curve="ratio"),
    *(Variant(name, s_curve="ratio") for name in CALIBRATIONS),
)
MARKET_METHODS = (
    Variant("current"),
    Variant("current_s_ratio", s_curve="ratio"),
    *(Variant(name, s_curve=curve) for name, (_, curve) in MARKET_VARIANTS.items()),
)
DEMAND_METHODS = (
    Variant("current"),
    Variant("d1_geometric"),
    Variant("d1_mean"),
    Variant("lq_half_s_ratio", s_curve="ratio"),
    Variant("lq_half_s_ratio_d1_geometric", s_curve="ratio"),
    Variant("lq_half_s_ratio_d1_mean", s_curve="ratio"),
)
METHODS = {
    "c1": C1_VARIANTS,
    "joint": ALL_VARIANTS,
    "calibration": CALIBRATION_VARIANTS,
    "market": MARKET_METHODS,
    "demand": DEMAND_METHODS,
}
SCOPES = ("all_212_candidates51", "supported_184_candidates45")


def exposure(orders: list[list[str]], universe: set[str], k: int) -> dict:
    counts = Counter(c for order in orders for c in order[:k])
    values = sorted(counts[c] for c in universe)
    total = sum(values)
    n = len(values)
    return {
        "slots": total,
        "never_n": sum(v == 0 for v in values),
        "max_locations": max(values),
        "top10_share": sum(sorted(values, reverse=True)[:10]) / total,
        "hhi": sum((v / total) ** 2 for v in values),
        "gini": sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(values)) / (n * total),
        "frequencies": {c: counts[c] for c in sorted(universe)},
    }


def metric(cases: list[dict], method: str, universe: set[str]) -> dict:
    summary = summarize(cases, method)
    ranks = [rank_of(c["orders"][method], c["target"]) for c in cases]
    return {
        **summary,
        "hit10_n": sum(r is not None and r <= 10 for r in ranks),
        "mean_target_rank": mean(r for r in ranks if r is not None),
        "exposure5": exposure([c["orders"][method] for c in cases], universe, 5),
        "exposure10": exposure([c["orders"][method] for c in cases], universe, 10),
        "target30_required_hits": math.ceil(0.3 * len(cases)),
        "target30_reached": summary["hit5"] >= 0.3,
    }


def folds(cases: list[dict], method: str) -> list[dict]:
    groups = [[] for _ in range(5)]
    for case in cases:
        # 같은 상권의 주소가 서로 다른 분할에 들어가지 않도록 라벨 없이 고정합니다.
        index = int(hashlib.sha256(case["cluster"].encode()).hexdigest()[:8], 16) % 5
        groups[index].append(case)
    return [
        {"fold": i, "n": len(group), "hit5_n": summarize(group, method)["hit5_n"]}
        for i, group in enumerate(groups)
        if group
    ]


def interval(cases: list[dict], a: str, b: str, k: int) -> dict:
    converted = [
        {
            "target": c["target"],
            "cluster": c["cluster"],
            "orders": {
                m: [c["target"]] if c["target"] in c["orders"][m][:k] else [] for m in (a, b)
            },
        }
        for c in cases
    ]
    return paired_cluster_interval(converted, a, b)


def run(source: Path, out: Path, stage: str) -> dict:
    if out.exists() or stage not in METHODS:
        raise ValueError("새 결과 경로와 유효한 비교 단계를 지정하세요.")
    variants = METHODS[stage]
    out.mkdir(parents=True)
    design = {
        "stage": stage,
        "variants": [describe(v) for v in variants],
        "calibrations": CALIBRATIONS if stage == "calibration" else {},
        "reference_min_clusters": MIN_REFERENCE_CLUSTERS,
        "reference_exclusion_radius_m": EXCLUSION_RADIUS_M,
        "reference_uses_target_labels": False,
        "market_variants": MARKET_VARIANTS if stage == "market" else {},
        "demand_variants": DEMAND_VARIANTS if stage == "demand" else {},
    }
    write_json(out / "design.json", design)
    original = source / "results.json"
    source_hash = sha256(original)
    reference = json.loads(original.read_text(encoding="utf-8"))
    if reference["settings"]["cutoff"] != "20252" or reference["paired_n"] != 212:
        raise ValueError("고정된 2025Q2·212곳 결과가 필요합니다.")
    all_codes = set(INDUSTRIES)
    supported = all_codes - set(INDUSTRIES_WITHOUT_SEOUL)
    cases, scores, case_hashes = [], [], {}
    reference_records, reference_manifest = [], {}
    preserved = changed = 0
    with block_network():
        if stage == "calibration":
            for c in reference["cases"]:
                path = source / "scores" / f"{c['id']}.json"
                if sha256(path) != reference["provenance"]["case_sha256"][c["id"]]:
                    raise ValueError("참고용 과거 점수가 달라졌습니다.")
                saved = json.loads(path.read_text(encoding="utf-8"))
                # 평가 라벨을 참고 계산에 전달하지 않습니다.
                reference_records.append(
                    {
                        "id": c["id"],
                        "cluster": c["cluster"],
                        "site": c["site"],
                        "scores": saved["scores"],
                    }
                )
        for c in reference["cases"]:
            p = source / "scores" / f"{c['id']}.json"
            if sha256(p) != reference["provenance"]["case_sha256"][c["id"]]:
                raise ValueError("고정된 사례 점수가 달라졌습니다.")
            case_hashes[p.name] = sha256(p)
            saved = json.loads(p.read_text(encoding="utf-8"))
            rows = copy.deepcopy(saved["scores"])
            for row in rows:
                row["items"].update(saved["continuous_S_items"][row["code"]])
            frozen_rows = copy.deepcopy(rows)
            calibration = None
            if reference_records:
                calibration = reference_for(reference_records, c["site"], c["cluster"])
                reference_manifest[c["id"]] = {
                    k: calibration[k] for k in ("training_ids", "excluded_ids")
                }
            orders, values_by_method = {}, {}
            for variant in variants:
                values = {r["code"]: score_row(r, variant) for r in rows}
                if stage in {"market", "demand"}:
                    market_name = (
                        "lq_half_s_ratio"
                        if stage == "demand" and variant.name.startswith("lq_")
                        else variant.name
                    )
                    values = {
                        r["code"]: apply_market(r, values[r["code"]], saved["data"], market_name)
                        for r in rows
                    }
                if stage == "demand":
                    values = {
                        r["code"]: apply_demand(r, values[r["code"]], variant.name) for r in rows
                    }
                if calibration is not None:
                    values = {
                        r["code"]: apply_calibration(
                            r, values[r["code"]], calibration, variant.name
                        )
                        for r in rows
                    }
                values_by_method[variant.name] = values
                orders[variant.name] = order_rows(rows, values)
                orders[variant.name + "_supported"] = order_rows(rows, values, supported)
                for row in rows:
                    for name, point in values[row["code"]]["item_points"].items():
                        old = row["items"][name]
                        if old["status"] != "observed":
                            if point is not None:
                                raise ValueError("미확인·미적용 점수를 채울 수 없습니다.")
                            preserved += 1
                        elif point != old["points"]:
                            changed += 1
                        if (
                            name.startswith("D")
                            and point != old["points"]
                            and not (stage == "demand" and name == "D1")
                        ):
                            raise ValueError("이번 비교에서 D 점수는 고정합니다.")
                if variant.name == "current":
                    if orders[variant.name] != saved["orders"]["past_continuous_80"]:
                        raise ValueError("기존 S 연속식 순위가 재현되지 않습니다.")
                    for code, value in values.items():
                        if not math.isclose(
                            value["normalized"],
                            saved["continuous_score80"][code]["normalized"],
                            rel_tol=1e-12,
                            abs_tol=1e-12,
                        ):
                            raise ValueError("기존 80점이 재현되지 않습니다.")
            commercial = saved["data"]["commercial_area"]["by_middle"]
            counts = {r["code"]: r["count"] for r in commercial}
            if set(counts) != all_codes or not saved["data"]["commercial_collection_complete"]:
                raise ValueError("같은 51업종의 완전한 점포 수 기준선이 필요합니다.")
            popular = sorted(counts, key=lambda code: (-counts[code], code))
            orders["popular"] = popular
            orders["popular_supported"] = [code for code in popular if code in supported]
            if rows != frozen_rows:
                raise ValueError("원본 항목별 상태·점수를 수정할 수 없습니다.")
            item_data = {
                r["code"]: {
                    "status": {k: r["items"][k]["status"] for k in C_ITEMS},
                    "values": {m: v[r["code"]] for m, v in values_by_method.items()},
                }
                for r in rows
            }
            scores.append({"id": c["id"], "industries": item_data})
            cases.append(
                {
                    "id": c["id"],
                    "target": c["target"],
                    "cluster": c["cluster"],
                    "site": c["site"],
                    "orders": orders,
                }
            )
    scopes = {}
    csv_metrics = []
    for label, universe, eligible, suffix in (
        (SCOPES[0], all_codes, cases, ""),
        (SCOPES[1], supported, [c for c in cases if c["target"] in supported], "_supported"),
    ):
        if len(eligible) != (212 if not suffix else 184):
            raise ValueError("검증 표본 수가 달라졌습니다.")
        names = [v.name for v in variants] + ["popular"]
        summaries = {name: metric(eligible, name + suffix, universe) for name in names}
        for name, summary in summaries.items():
            summary["folds"] = folds(eligible, name + suffix)
            if name not in {"current", "popular"}:
                summary["hit5_delta_vs_current"] = interval(
                    eligible, "current" + suffix, name + suffix, 5
                )
                summary["hit10_delta_vs_current"] = interval(
                    eligible, "current" + suffix, name + suffix, 10
                )
            summary["hit5_delta_vs_popular"] = interval(
                eligible, "popular" + suffix, name + suffix, 5
            )
            csv_metrics.append(
                {
                    "범위": label,
                    "비교안": name,
                    "위치수": len(eligible),
                    "TOP5일치수": summary["hit5_n"],
                    "TOP5비율": summary["hit5"],
                    "TOP10일치수": summary["hit10_n"],
                    "TOP10비율": summary["hit10"],
                    "평균순위": summary["mean_target_rank"],
                    "미등장업종수": summary["exposure5"]["never_n"],
                    "최다업종등장수": summary["exposure5"]["max_locations"],
                    "상위10업종점유율": summary["exposure5"]["top10_share"],
                    "지니계수": summary["exposure5"]["gini"],
                }
            )
        scopes[label] = summaries
    csv_file(out / "비교안별_포함률과_추천쏠림.csv", csv_metrics)
    write_json(out / "scores.json", scores)
    if reference_manifest:
        write_json(out / "reference-exclusions.json", reference_manifest)
    result = {
        "kind": "fixed-past80-C1-S-development-experiment",
        "stage": stage,
        "cutoff": "20252",
        "variants": [describe(v) for v in variants],
        "design": design,
        "scopes": scopes,
        "cases": cases,
        "checks": {
            "unknown_or_na_items_preserved": preserved,
            "observed_item_adjustments": changed,
            "baseline_reproduced": True,
        },
        "limits": [
            "같은 개선용 표본의 재사용이며 독립 검증 아님",
            "상권별 분할 결과는 민감도 확인이며 이미 본 표본을 새 검증 표본으로 바꾸지 않음",
            "30%는 TOP5 포함률 목표. 추천 빈도를 강제로 균등하게 만들지 않음",
            "C1 중립 고정은 정보 기여도 확인용이며 채택 권고 아님",
            "분포 보정은 같은 개선용 표본 중 다른 상권을 참고한 탐색이며 독립 검증 아님",
        ],
        "provenance": {
            "source_results_sha256": source_hash,
            "source_case_sha256": case_hashes,
            "source_unchanged": sha256(original) == source_hash,
            "scores_sha256": sha256(out / "scores.json"),
            "code_sha256": {
                p.name: sha256(p)
                for p in (
                    Path(__file__),
                    Path(__file__).with_name("rank_variant.py"),
                    Path(__file__).with_name("rank_calibration.py"),
                    Path(__file__).with_name("rank_market.py"),
                    Path(__file__).with_name("rank_demand.py"),
                )
            },
            "analysis_api_calls": 0,
            "llm_calls": 0,
            "operating_changed": False,
        },
    }
    if not result["provenance"]["source_unchanged"]:
        raise ValueError("원본 결과가 달라졌습니다.")
    write_json(out / "results.json", result)
    snapshot = out / "source-snapshot"
    snapshot.mkdir()
    for name, expected in result["provenance"]["code_sha256"].items():
        path = Path(__file__).with_name(name)
        if sha256(path) != expected:
            raise ValueError("실행 중 실험 코드가 달라졌습니다.")
        (snapshot / name).write_bytes(path.read_bytes())
    return result


def main():
    parser = argparse.ArgumentParser(description="C1·S 점수 격차를 오프라인에서 비교합니다.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stage", choices=METHODS, default="c1")
    args = parser.parse_args()
    result = run(args.source, args.out, args.stage)
    print(
        json.dumps(
            {
                scope: {
                    m: {
                        "hit5": v["hit5_n"],
                        "hit10": v["hit10_n"],
                        "mean_rank": v["mean_target_rank"],
                        "never": v["exposure5"]["never_n"],
                        "concentration": v["exposure5"]["top10_share"],
                    }
                    for m, v in values.items()
                }
                for scope, values in result["scopes"].items()
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
