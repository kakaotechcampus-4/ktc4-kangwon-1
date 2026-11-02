"""서울 같은 분기의 통행 규모를 맞춘 경쟁 백분위를 계산합니다."""

import math
from bisect import bisect_left, bisect_right

from app.agents.floating_population.geo import overlapping_areas
from app.agents.floating_population.models import quarter_days
from app.agents.floating_population.numeric import complete_sum
from app.geo import to_epsg5181

MODES = {
    "count": ("all", 0.0),
    "near_sqrt": ("near", 0.5),
    "all_sqrt": ("all", 0.5),
    "near_linear": ("near", 1.0),
}


def matching_daily(site: dict, areas: list, totals: dict) -> dict:
    hits = overlapping_areas(areas, *to_epsg5181(site["latitude"], site["longitude"]), 500)
    codes = [a.trdar_cd for a, _ in hits if a.trdar_cd in totals]
    values = [totals[c] for c in codes]
    total = complete_sum(values)
    daily = (
        round(total / len(codes) / quarter_days("20252"), 1)
        if codes and total is not None
        else None
    )
    return {"daily": daily, "observed_area_codes": codes, "observed_area_n": len(codes)}


def competition_fraction(
    count: int, daily: float | None, reference: list[tuple[int, float | None]], kind: str, mode: str
) -> dict:
    if mode not in MODES or kind not in ("근처형", "모임형") or type(count) is not int or count < 0:
        raise ValueError("동일한 경쟁 유형·실제 점포 수·고정 비교안이 필요합니다.")
    scope, alpha = MODES[mode]
    if scope == "near" and kind != "근처형":
        alpha = 0

    def valid_daily(v):
        return type(v) in (int, float) and math.isfinite(v) and v > 0

    if alpha and not valid_daily(daily):
        return {"available": False, "reason": "missing_actual_daily_population"}
    if any(type(c) is not int or c < 0 for c, _ in reference):
        raise ValueError("참고 점포 수가 유효해야 합니다.")
    selected = [(c, d) for c, d in reference if not alpha or valid_daily(d)]
    if len(selected) < 20:
        return {"available": False, "reason": "insufficient_matched_reference"}
    values = sorted(c / (d**alpha) if alpha else float(c) for c, d in selected)
    local = count / (daily**alpha) if alpha else float(count)
    q = (bisect_left(values, local) + bisect_right(values, local)) / (2 * len(values))
    return {
        "available": True,
        "quantile": q,
        "profile_fraction": q if kind == "모임형" else 1 - q,
        "demand_alpha": alpha,
        "observed_competition_metric": local,
        "reference_n": len(values),
    }
