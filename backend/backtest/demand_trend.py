"""같은 상권·같은 분기의 실제 주변 통행량으로 업종별 D4를 비교합니다."""

from bisect import bisect_right

from app.agents.floating_population.models import quarter_days
from app.agents.floating_population.numeric import complete_sum
from backtest.rank_d_smooth import TREND_EDGES, smooth_grade

QUARTERS = ("20242", "20252")
MODES = ("control", "time_yoy", "age_yoy", "mean_marginal_yoy")


def observed_change(
    main_codes: list[str], panels: dict, field: str, categories: list[str] | None = None
) -> dict:
    codes = {q: {c for c in main_codes if c in panels[q]} for q in QUARTERS}
    if not codes[QUARTERS[0]] or codes[QUARTERS[0]] != codes[QUARTERS[1]]:
        return {"available": False, "reason": "different_or_empty_area_sets"}
    daily = {}
    for quarter in QUARTERS:
        values = []
        for code in sorted(codes[quarter]):
            record = panels[quarter][code]
            values.append(
                record.total
                if field == "total"
                else complete_sum(getattr(record, field).get(k) for k in categories)
            )
        total = complete_sum(values)
        if total is None:
            return {"available": False, "reason": "missing_observed_segment"}
        daily[quarter] = round(total / quarter_days(quarter), 1)
    old, new = (daily[q] for q in QUARTERS)
    if old <= 0:
        return {"available": False, "reason": "zero_previous_denominator"}
    return {
        "available": True,
        "yoy": round((new - old) / old, 4),
        "daily": daily,
        "area_codes": sorted(codes[QUARTERS[0]]),
        "source_field": field,
        "categories": categories,
    }


def d4_fraction(change: float) -> float:
    value = 100 * change
    step = bisect_right(TREND_EDGES, value)
    smooth = smooth_grade(value, TREND_EDGES)
    return (0.25 * step + 0.75 * smooth) / 4


def segment_changes(profile: dict, main_codes: list[str], panels: dict) -> dict:
    result = {"total": observed_change(main_codes, panels, "total")}
    for name, field, key in (
        ("time", "by_time", "primary_bands"),
        ("age", "by_age", "target_age_bands"),
    ):
        categories = [x for x in profile.get(key, "").split(";") if x]
        result[name] = (
            observed_change(main_codes, panels, field, categories)
            if categories
            else {"available": False, "reason": "no_configured_segment"}
        )
    result["age_is_floating_proxy_for_D3_population"] = profile.get("target_population") not in (
        "",
        None,
        "유동",
    )
    return result


def replacement(evidence: dict, mode: str) -> dict:
    if mode not in MODES:
        raise ValueError("사전에 고정한 D4 비교안이 필요합니다.")
    if mode == "control":
        return {"applied": False}
    names = ["time"] if mode == "time_yoy" else ["age"] if mode == "age_yoy" else ["time", "age"]
    observed = [evidence[n]["yoy"] for n in names if evidence[n]["available"]]
    if not observed:
        return {"applied": False, "reason": "no_observed_target_segment"}
    change = sum(observed) / len(observed)
    return {
        "applied": True,
        "fraction": d4_fraction(change),
        "change": change,
        "segment_sources": [n for n in names if evidence[n]["available"]],
        "does_not_infer_joint_age_time_counts": True,
    }
