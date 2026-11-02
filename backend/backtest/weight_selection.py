"""관측 상태·추정 구분을 보존하는 가중치 계산과 지역 분리 선택입니다."""

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass

from app.agentic.scoring import WEIGHTS, valid
from app.geo import haversine_m
from backtest.followup import C_ITEMS
from backtest.rank_experiment import exposure

ORIGINAL_WEIGHTS = (35, 15, 30)
RECIPES = (
    "current",
    "lq_half_s_ratio",
    "lq_half_s_ratio_sparse_quadratic",
    "lq_half_s_ratio_sparse_quadratic_regional25",
)
WEIGHT_GRID = tuple(
    (d, c, 80 - d - c) for d in (20, 35, 50) for c in (5, 15, 25) if 15 <= 80 - d - c <= 50
)
EXTENDED_GRID = tuple(
    (d, c, 80 - d - c) for d in range(5, 65, 5) for c in range(5, 65, 5) if 15 <= 80 - d - c <= 50
)
TEMPERATURE = 10.0
BUFFER_M = 1000
FOLD_SEED = 20261030


@dataclass(frozen=True)
class Configuration:
    recipe: str
    weights: tuple[int, int, int]

    @property
    def name(self) -> str:
        return self.recipe + "_w" + "_".join(map(str, self.weights))


CONFIGURATIONS = tuple(Configuration(r, w) for r in RECIPES for w in WEIGHT_GRID)
CURRENT = Configuration("current", ORIGINAL_WEIGHTS).name


def features_for(statuses: dict, value: dict) -> dict:
    status = {name: statuses[name] for name in C_ITEMS}
    observed = {name: value["item_points"][name] for name in C_ITEMS}
    estimates = value.get("estimated_item_points", {})
    if not estimates.keys() <= set(C_ITEMS):
        raise ValueError("고정 평가 항목 밖의 추정 기여가 있습니다.")
    for name in C_ITEMS:
        state, point = status[name], observed[name]
        if state not in {"observed", "unknown", "n.a."}:
            raise ValueError("알 수 없는 관측 상태입니다.")
        if state == "observed":
            if not valid(point) or not 0 <= point <= WEIGHTS[name]:
                raise ValueError("관측 점수가 항목 배점 범위 밖입니다.")
        elif point is not None:
            raise ValueError("미확인·미적용을 관측 점수로 바꿀 수 없습니다.")
        if name in estimates and (
            state != "unknown"
            or not valid(estimates[name])
            or not 0 <= estimates[name] <= WEIGHTS[name]
        ):
            raise ValueError("추정 기여는 미확인 항목 안에서 별도로 계산해야 합니다.")
    points = sum(v for v in observed.values() if v is not None) + sum(estimates.values())
    applicable = sum(WEIGHTS[n] for n, state in status.items() if state != "n.a.")
    if not math.isclose(points, value["points"], abs_tol=1e-10) or not math.isclose(
        applicable, value["applicable"], abs_tol=1e-10
    ):
        raise ValueError("저장된 점수와 항목별 관측·추정·적용 배점이 다릅니다.")
    if applicable <= 0 or not math.isclose(
        80 * points / applicable, value["normalized"], abs_tol=1e-10
    ):
        raise ValueError("원래80점이 재현되지 않습니다.")
    return {
        "status": status,
        "observed": observed,
        "estimated": dict(estimates),
        "frozen_score": value["normalized"],
    }


def weighted_score(
    features: dict, weights: tuple[int, int, int], grid: tuple = WEIGHT_GRID
) -> dict:
    if weights not in grid or sum(weights) != 80 or weights[2] < 15 or min(weights) <= 0:
        raise ValueError("S 배점15점 이상을 유지하는 사전 고정 가중치만 허용합니다.")
    factors = {"D": weights[0] / 35, "C": weights[1] / 15, "S": weights[2] / 30}
    applicable = sum(WEIGHTS[n] * factors[n[0]] for n in C_ITEMS if features["status"][n] != "n.a.")
    observed = sum(
        point * factors[n[0]] for n, point in features["observed"].items() if point is not None
    )
    estimated = sum(point * factors[n[0]] for n, point in features["estimated"].items())
    score = 80 * (observed + estimated) / applicable
    if weights == ORIGINAL_WEIGHTS:
        if not math.isclose(score, features["frozen_score"], abs_tol=1e-10):
            raise ValueError("원래 배점에서 동결 점수가 재현되지 않습니다.")
        # 동점 부근의 부동소수점 합산 차이가 기준 순위를 바꾸지 않게 원래 수치를 보존합니다.
        score = features["frozen_score"]
    return {
        "normalized": score,
        "applicable": applicable,
        "observed_points": observed,
        "estimated_points": estimated,
    }


def order_scores(scores: dict[str, float], tie_metadata: dict) -> list[str]:
    return sorted(
        scores,
        key=lambda c: (
            -(scores[c] + tie_metadata[c]["adjustment"]),
            -(tie_metadata[c]["coverage"] or 0),
            c,
        ),
    )


def assign_folds(locations: list[dict], fold_n: int = 5) -> dict[str, int]:
    groups = defaultdict(list)
    for case in locations:
        groups[case["district"]].append(case["id"])
    if len(groups) < fold_n:
        raise ValueError("평가 분할 수 이상의 서로 다른 자치구가 필요합니다.")
    # 자치구를 분리하면서 주소 수만으로 분할 크기를 맞춥니다. 정답·점수는 읽지 않습니다.
    ordered = sorted(
        groups,
        key=lambda g: (-len(groups[g]), hashlib.sha256(f"{FOLD_SEED}|{g}".encode()).hexdigest()),
    )
    sizes, assigned = [0] * fold_n, {}
    for district in ordered:
        fold = min(range(fold_n), key=lambda i: (sizes[i], i))
        for key in groups[district]:
            assigned[key] = fold
        sizes[fold] += len(groups[district])
    return assigned


def split_training(locations: list[dict], held_ids: set[str]) -> dict:
    held = [c for c in locations if c["id"] in held_ids]
    if not held or len(held) != len(held_ids):
        raise ValueError("평가 위치가 비었거나 원래 표본에 없습니다.")
    districts = {c["district"] for c in held}
    areas = {c["cluster"] for c in held}
    training, excluded = [], {}
    for case in locations:
        key = case["id"]
        if key in held_ids:
            continue
        if case["district"] in districts:
            excluded[key] = "same_district"
        elif case["cluster"] in areas:
            excluded[key] = "same_market_area"
        elif any(
            haversine_m(
                case["site"]["latitude"],
                case["site"]["longitude"],
                other["site"]["latitude"],
                other["site"]["longitude"],
            )
            <= BUFFER_M
            for other in held
        ):
            excluded[key] = "within1000m_of_evaluation"
        else:
            training.append(key)
    if not training:
        raise ValueError("공간 제외 후 학습 위치가 없습니다.")
    return {
        "training_ids": sorted(training),
        "held_ids": sorted(held_ids),
        "excluded_ids": excluded,
        "held_districts": sorted(districts),
    }


def negative_log_probability(scores: dict[str, float], target: str) -> float:
    if target not in scores:
        raise ValueError("실제 업종은 고정 후보 목록에 있어야 합니다.")
    scaled = {c: v / TEMPERATURE for c, v in scores.items()}
    maximum = max(scaled.values())
    return (
        maximum
        + math.log(math.fsum(math.exp(v - maximum) for v in scaled.values()))
        - scaled[target]
    )


def select_configuration(
    training_cases: list[dict],
    predictions: dict,
    orders: dict,
    configurations: tuple = CONFIGURATIONS,
) -> dict:
    if not training_cases:
        raise ValueError("가중치 선택에 학습 사례가 필요합니다.")
    keys = [c["id"] for c in training_cases]
    if len(set(keys)) != len(keys):
        raise ValueError("학습 사례ID가 중복됩니다.")
    universe = set(predictions[keys[0]][CURRENT])
    for key in keys:
        if any(
            set(predictions[key][c.name]) != universe
            or len(orders[key][c.name]) != len(universe)
            or set(orders[key][c.name]) != universe
            for c in configurations
        ):
            raise ValueError("학습 점수와 순위는 중복 없는 같은 후보 목록을 가져야 합니다.")
    baseline = exposure([orders[k][CURRENT] for k in keys], universe, 5)
    candidates = {}
    for config in configurations:
        name = config.name
        by_cluster = defaultdict(list)
        for case in training_cases:
            value = negative_log_probability(predictions[case["id"]][name], case["target"])
            by_cluster[case["cluster"]].append(value)
        loss = math.fsum(
            math.fsum(sorted(values)) / len(values) for _, values in sorted(by_cluster.items())
        ) / len(by_cluster)
        frequencies = exposure([orders[k][name] for k in keys], universe, 5)
        eligible = (
            frequencies["gini"] <= baseline["gini"] + 1e-12
            and frequencies["top10_share"] <= baseline["top10_share"] + 1e-12
            and frequencies["never_n"] <= baseline["never_n"]
            and frequencies["max_locations"] <= baseline["max_locations"]
        )
        candidates[name] = {
            "cluster_mean_log_loss": loss,
            "eligible": eligible,
            "exposure5": frequencies,
            "training_hit5_n": sum(
                c["target"] in orders[c["id"]][name][:5] for c in training_cases
            ),
        }
    feasible = [c for c in configurations if candidates[c.name]["eligible"]]
    if not feasible:
        raise ValueError("원래 점수식조차 쏠림 제약을 만족하지 않습니다.")
    winner = min(
        feasible,
        key=lambda c: (
            candidates[c.name]["cluster_mean_log_loss"],
            sum((a - b) ** 2 for a, b in zip(c.weights, ORIGINAL_WEIGHTS, strict=True)),
            RECIPES.index(c.recipe),
            c.name,
        ),
    )
    return {
        "configuration": winner.name,
        "recipe": winner.recipe,
        "weights": winner.weights,
        "training_n": len(keys),
        "training_area_n": len(by_cluster),
        "feasible_n": len(feasible),
        "candidates": candidates,
        "selection_uses_evaluation_labels": False,
    }
