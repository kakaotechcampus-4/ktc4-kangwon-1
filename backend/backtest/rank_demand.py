"""D1의 두 관측 근거를 결합하는 규칙만 바꾸는 진단입니다."""

import math

from app.agentic.scoring import valid

DEMAND_VARIANTS = {
    "d1_geometric": "geometric",
    "d1_mean": "mean",
    "lq_half_s_ratio_d1_geometric": "geometric",
    "lq_half_s_ratio_d1_mean": "mean",
}


def apply_demand(row: dict, base: dict, name: str) -> dict:
    if name not in DEMAND_VARIANTS:
        return base
    item = row["items"]["D1"]
    value = item.get("value")
    # 종일형은 규모 하나만 사용하므로 시간대 적합성과 결합하지 않습니다.
    if item["status"] != "observed" or not isinstance(value, dict):
        return base
    ratio, percentile = value.get("r"), value.get("p")
    if not valid(ratio) or not valid(percentile):
        raise ValueError("관측 D1의 시간대 적합성·규모 백분위가 필요합니다.")
    fit = sum(ratio >= x for x in (0.8, 0.95, 1.05, 1.2))
    scale = sum(percentile >= x for x in (20, 40, 60, 80))
    if item["grade"] != min(fit, scale):
        raise ValueError("원래 D1의 최소 등급을 재현할 수 없습니다.")
    grade = math.sqrt(fit * scale) if DEMAND_VARIANTS[name] == "geometric" else (fit + scale) / 2
    points, grades = dict(base["item_points"]), dict(base["item_grades"])
    points["D1"], grades["D1"] = 10 * grade / 4, grade
    total = sum(v for v in points.values() if v is not None)
    return {
        **base,
        "points": total,
        "normalized": 80 * total / base["applicable"],
        "item_points": points,
        "item_grades": grades,
        "demand": {"fit_grade": fit, "scale_grade": scale, "combination": DEMAND_VARIANTS[name]},
    }
