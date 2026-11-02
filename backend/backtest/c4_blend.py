"""C4를 고정하고 기존 점수식의 양수 결합만 비교합니다."""

from dataclasses import dataclass

from app.industries.catalog import INDUSTRIES_WITHOUT_SEOUL
from backtest.c4_policy import POLICIES, score_policy
from backtest.rank_experiment import metric
from backtest.smooth_selection import blend_scores


@dataclass(frozen=True)
class BlendConfiguration:
    name: str
    anchor: str
    accuracy_fraction: float


CONFIGURATIONS = (
    BlendConfiguration("retained_C4", "retained_D75", 0),
    BlendConfiguration("balanced_C4", "balanced57", 0),
    BlendConfiguration("accuracy_C4", "retained_D75", 1),
    *(BlendConfiguration(f"retained_accuracy{n}", "retained_D75", n / 100) for n in (25, 50, 75)),
    *(BlendConfiguration(f"balanced_accuracy{n}", "balanced57", n / 100) for n in (25, 50, 75)),
)
CONTROL = "retained_C4"
FACILITY_POLICY = next(p for p in POLICIES if p.name == "mean_mild_low_confidence_half")


def score_blend(common80: dict, applicable: dict, profiles: dict, components: dict, config) -> dict:
    if config not in CONFIGURATIONS:
        raise ValueError("사전에 고정한 점수식 결합만 허용합니다.")
    blended = blend_scores(
        common80[config.anchor], common80["accuracy64"], config.accuracy_fraction
    )
    if not blended.keys() == applicable.keys() == profiles.keys() == components.keys():
        raise ValueError("기존 점수·배점·시설 관측의 후보 목록이 같아야 합니다.")
    details = {
        c: score_policy(value, applicable[c], profiles[c], components[c], FACILITY_POLICY)
        for c, value in blended.items()
    }
    return {
        "values": {c: value["normalized"] for c, value in details.items()},
        "common80": blended,
        "C4_details": details,
    }


def evaluate(cases: list[dict], orders: dict, method: str, universe: set[str]) -> dict:
    selected = [
        {
            **c,
            "orders": {method: [code for code in orders[c["id"]][method] if code in universe]},
        }
        for c in cases
        if c["target"] in universe
    ]
    if not selected:
        raise ValueError("평가 범위에 실제 업종 사례가 없습니다.")
    return metric(selected, method, universe)


def no_worse(candidate: dict, baseline: dict) -> bool:
    return (
        candidate["hit5_n"] >= baseline["hit5_n"]
        and candidate["hit10_n"] >= baseline["hit10_n"]
        and candidate["exposure5"]["never_n"] <= baseline["exposure5"]["never_n"]
        and candidate["exposure5"]["max_locations"] <= baseline["exposure5"]["max_locations"]
        and candidate["exposure5"]["gini"] <= baseline["exposure5"]["gini"] + 1e-12
        and candidate["exposure5"]["top10_share"] <= baseline["exposure5"]["top10_share"] + 1e-12
    )


def select_blend(training: list[dict], predictions: dict, orders: dict) -> dict:
    ids = [c["id"] for c in training]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("중복 없는 학습 위치가 필요합니다.")
    universe = set(predictions[ids[0]][CONTROL])
    if any(c["target"] not in universe for c in training):
        raise ValueError("학습 실제 업종은 고정 후보 목록에 있어야 합니다.")
    for key in ids:
        for config in CONFIGURATIONS:
            if (
                set(predictions[key][config.name]) != universe
                or set(orders[key][config.name]) != universe
                or len(orders[key][config.name]) != len(universe)
            ):
                raise ValueError("학습 순위·점수는 동일하고 중복 없는 후보 목록이어야 합니다.")
    supported = universe - set(INDUSTRIES_WITHOUT_SEOUL)
    details = {
        config.name: {
            "primary": evaluate(training, orders, config.name, universe),
            "supported": evaluate(training, orders, config.name, supported),
        }
        for config in CONFIGURATIONS
    }
    for item in details.values():
        item["eligible"] = all(
            no_worse(item[s], details[CONTROL][s]) for s in ("primary", "supported")
        )
    eligible = [c for c in CONFIGURATIONS if details[c.name]["eligible"]]
    if not eligible:
        raise ValueError("비교 기준이 학습 조건을 만족하지 않습니다.")
    winner = min(
        eligible,
        key=lambda c: (
            -details[c.name]["primary"]["hit5_n"],
            -details[c.name]["supported"]["hit5_n"],
            -details[c.name]["primary"]["hit10_n"],
            details[c.name]["primary"]["exposure5"]["gini"],
            c.name != CONTROL,
            c.accuracy_fraction,
            c.name,
        ),
    )
    return {
        "method": winner.name,
        "training_ids": sorted(ids),
        "training_n": len(ids),
        "candidates": details,
        "selection_uses_held_labels": False,
        "scope": "C4_fixed_combination_selection_only",
    }
