"""학습 지역에서만 D 연속화 강도를 고르고 추천 분포 악화를 차단합니다."""

import math
from collections import defaultdict

from app.agentic.scoring import valid
from backtest.rank_experiment import exposure
from backtest.weight_selection import negative_log_probability

FRACTIONS = {"d_0": 0.0, "d_25": 0.25, "d_50": 0.5, "d_75": 0.75, "d_100": 1.0}


def blend_scores(base: dict, continuous: dict, fraction: float) -> dict:
    if fraction not in FRACTIONS.values() or not base or base.keys() != continuous.keys():
        raise ValueError("같은 업종 후보와 미리 정한 D 변경 비중이 필요합니다.")
    if any(not valid(v) or not 0 <= v <= 80 for v in (*base.values(), *continuous.values())):
        raise ValueError("원래 점수와 연속화 점수는 유효한 80점 환산값이어야 합니다.")
    # 양 끝에서는 동점 부근 합산 오차가 원래 순위를 바꾸지 않게 합니다.
    return (
        dict(base)
        if fraction == 0
        else dict(continuous)
        if fraction == 1
        else {code: value + fraction * (continuous[code] - value) for code, value in base.items()}
    )


def select_fraction(training: list[dict], predictions: dict, orders: dict) -> dict:
    keys = [c["id"] for c in training]
    if not training or len(set(keys)) != len(keys):
        raise ValueError("중복 없는 학습 사례가 필요합니다.")
    universe = set(predictions[keys[0]]["d_0"])
    for key in keys:
        if any(
            set(predictions[key][m]) != universe
            or set(orders[key][m]) != universe
            or len(orders[key][m]) != len(universe)
            for m in FRACTIONS
        ):
            raise ValueError("학습 점수·순위는 같은 후보 범위를 가져야 합니다.")
    baseline = exposure([orders[key]["d_0"] for key in keys], universe, 5)
    baseline_hits = sum(c["target"] in orders[c["id"]]["d_0"][:5] for c in training)
    details = {}
    for method in FRACTIONS:
        by_area = defaultdict(list)
        for case in training:
            key = case["id"]
            by_area[case["cluster"]].append(
                (
                    int(case["target"] in orders[key][method][:5]),
                    negative_log_probability(predictions[key][method], case["target"]),
                )
            )
        cluster_hits = math.fsum(
            sum(v[0] for v in rows) / len(rows) for rows in by_area.values()
        ) / len(by_area)
        loss = math.fsum(
            math.fsum(v[1] for v in rows) / len(rows) for rows in by_area.values()
        ) / len(by_area)
        frequencies = exposure([orders[key][method] for key in keys], universe, 5)
        hit_n = sum(c["target"] in orders[c["id"]][method][:5] for c in training)
        eligible = (
            frequencies["gini"] <= baseline["gini"] + 1e-12
            and frequencies["top10_share"] <= baseline["top10_share"] + 1e-12
            and frequencies["never_n"] <= baseline["never_n"]
            and frequencies["max_locations"] <= baseline["max_locations"]
            and hit_n >= baseline_hits
        )
        details[method] = {
            "fraction": FRACTIONS[method],
            "cluster_mean_hit5": cluster_hits,
            "cluster_mean_log_loss": loss,
            "training_hit5_n": hit_n,
            "exposure5": frequencies,
            "eligible": eligible,
        }
    feasible = [m for m in FRACTIONS if details[m]["eligible"]]
    winner = min(
        feasible,
        key=lambda m: (
            -details[m]["cluster_mean_hit5"],
            details[m]["cluster_mean_log_loss"],
            FRACTIONS[m],
        ),
    )
    return {
        "method": winner,
        "fraction": FRACTIONS[winner],
        "training_n": len(keys),
        "training_area_n": len(by_area),
        "candidates": details,
        "selection_uses_evaluation_labels": False,
    }
