"""실제 과거 폐업0건과 원천 누락을 구분하는 S4 변화량 비교입니다."""

from app.industries.catalog import INDUSTRY_TO_SEOUL
from backtest.source_provenance import required_quarters, totals, valid_counts

MODES = ("control", "zero_old_only", "rate_difference_complete")


def difference_evidence(code: str, quarters: list[str], local: dict, city: dict) -> dict:
    sources = INDUSTRY_TO_SEOUL.get(code, ())
    if not sources:
        return {"available": False, "reason": "unsupported_source"}
    window = required_quarters("S4", quarters)
    for name, panel in (("local", local), ("city", city)):
        if any(not valid_counts(panel.get(q, {}).get(s)) for q in window for s in sources):
            return {"available": False, "reason": name + "_required_row_or_counts_missing"}
    old, recent = totals(local, quarters[:4], sources), totals(local, quarters[-4:], sources)
    city_old, city_recent = (
        totals(city, quarters[:4], sources),
        totals(city, quarters[-4:], sources),
    )
    if min(old[0], recent[0], city_old[0], city_recent[0]) <= 0:
        return {"available": False, "reason": "zero_exposure_denominator"}
    old_rate, recent_rate = old[2] / old[0], recent[2] / recent[0]
    city_old_rate, city_recent_rate = city_old[2] / city_old[0], city_recent[2] / city_recent[0]
    scale = (city_old_rate + city_recent_rate) / 2
    if scale <= 0:
        return {"available": False, "reason": "zero_city_change_scale"}
    z = ((recent_rate - old_rate) - (city_recent_rate - city_old_rate)) / scale
    fraction = 0.5 - 0.5 * z / (1 + abs(z))
    exposure = min(old[0], recent[0])
    reliability = min(1, exposure / 40) ** 2
    return {
        "available": True,
        "old_counts": old,
        "recent_counts": recent,
        "city_old_counts": city_old,
        "city_recent_counts": city_recent,
        "normalized_change_difference": z,
        "undiscounted_fraction": fraction,
        "effective_exposure": exposure,
        "reliability": reliability,
        "fraction": fraction * reliability,
        "source_kind": "derived_change_from_complete_required_rows",
        "missing_rows_filled": False,
    }


def changed_fraction(state: str, evidence: dict, mode: str) -> float | None:
    if state not in {"observed", "unknown", "n.a."} or mode not in MODES:
        raise ValueError("원래 관측 상태와 사전에 고정한 S4 비교안이 필요합니다.")
    if mode == "control" or state == "n.a." or not evidence["available"]:
        return None
    exposure = evidence["effective_exposure"]
    if state == "observed" and exposure < 40:
        raise ValueError("기존 관측 S4의 과거·최근 노출량 조건과 다릅니다.")
    if mode == "zero_old_only" and not (
        state == "unknown" and evidence["old_counts"][2] == 0 and exposure >= 40
    ):
        return None
    return evidence["fraction"]
