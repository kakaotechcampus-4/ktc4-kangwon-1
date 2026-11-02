"""기존 D 경계를 유지하면서 관측값의 계단형 등급만 연속화합니다."""

from bisect import bisect_right

from app.agentic.scoring import WEIGHTS, valid

RATIO_EDGES = (0.8, 0.95, 1.05, 1.2)
PERCENTILE_EDGES = (20, 40, 60, 80)
TREND_EDGES = (-10, -3, 3, 10)
SMOOTH_DOMAINS = {"secondary": ("D2", "D3", "D4"), "all": ("D1", "D2", "D3", "D4")}


def smooth_grade(value: float, edges: tuple) -> float:
    if (
        not valid(value)
        or len(edges) != 4
        or any(a >= b for a, b in zip(edges, edges[1:], strict=False))
    ):
        raise ValueError("유효한 관측값과 증가하는 기존 경계 네 개가 필요합니다.")
    knots = (edges[0] - (edges[1] - edges[0]) / 2, *edges, edges[-1] + (edges[-1] - edges[-2]) / 2)
    grades = (0, 0.5, 1.5, 2.5, 3.5, 4)
    if value <= knots[0]:
        return 0.0
    if value >= knots[-1]:
        return 4.0
    upper = bisect_right(knots, value)
    lower = upper - 1
    fraction = (value - knots[lower]) / (knots[upper] - knots[lower])
    return grades[lower] + fraction * (grades[upper] - grades[lower])


def demand_adjustment(items: dict, mode: str, d_weight: float) -> dict:
    if mode not in SMOOTH_DOMAINS or not valid(d_weight) or d_weight <= 0:
        raise ValueError("고정 비교 항목과 양수 D 배점이 필요합니다.")
    changes = {}
    for name in SMOOTH_DOMAINS[mode]:
        item = items[name]
        if item["status"] != "observed":
            continue
        value = item.get("value")
        if name == "D1":
            # 종일형에는 저장된 백분위가 없으므로 원래 규모 등급을 보존합니다.
            if not isinstance(value, dict):
                continue
            ratio, percentile = value["r"], value["p"]
            old = min(bisect_right(RATIO_EDGES, ratio), bisect_right(PERCENTILE_EDGES, percentile))
            grade = min(
                smooth_grade(ratio, RATIO_EDGES), smooth_grade(percentile, PERCENTILE_EDGES)
            )
        else:
            if name == "D3":
                value = value["r"]
            if name == "D4":
                value *= 100
            edges = TREND_EDGES if name == "D4" else RATIO_EDGES
            grade, old = smooth_grade(value, edges), bisect_right(edges, value)
        if item["grade"] != old or item["points"] != WEIGHTS[name] * old / 4:
            raise ValueError("기존 D 경계·관측 점수가 재현되지 않습니다.")
        delta = WEIGHTS[name] * (grade - old) / 4 * d_weight / 35
        changes[name] = {"source_grade": old, "new_grade": grade, "weighted_delta": delta}
    return {"weighted_delta": sum(v["weighted_delta"] for v in changes.values()), "items": changes}
