"""같은 모집단·같은 관측 상권의 실제 고객 연령 변화만 계산합니다."""

from app.agents.floating_population.models import quarter_days
from app.agents.floating_population.numeric import complete_sum

QUARTERS = ("20242", "20252")
MODES = ("control", "customer_yoy", "customer_relative", "customer_half")


def age_change(codes: list[str], panels: dict, ages: list[str], *, flow: bool) -> dict:
    observed = {q: {code for code in codes if code in panels[q]} for q in QUARTERS}
    if not observed[QUARTERS[0]] or observed[QUARTERS[0]] != observed[QUARTERS[1]]:
        return {"available": False, "reason": "different_or_empty_observed_area_sets"}
    levels = {}
    for q in QUARTERS:
        total = complete_sum(
            complete_sum(panels[q][c].by_age.get(age) for age in ages) for c in sorted(observed[q])
        )
        if total is None:
            return {"available": False, "reason": "missing_actual_age_value"}
        levels[q] = round(total / quarter_days(q), 1) if flow else total
    previous, current = (levels[q] for q in QUARTERS)
    if previous <= 0:
        return {"available": False, "reason": "zero_previous_age_denominator"}
    return {
        "available": True,
        "yoy": round((current - previous) / previous, 4),
        "levels": levels,
        "area_codes": sorted(observed[QUARTERS[0]]),
        "unit": "persons_per_day" if flow else "persons_stock",
        "age_bands": ages,
    }


def evidence_for(profile: dict, main_codes: list[str], panels: dict, city_cache: dict) -> dict:
    kind = profile.get("target_population")
    ages = [v for v in profile.get("target_age_bands", "").split(";") if v]
    if kind not in panels or not ages:
        return {"available": False, "reason": "no_configured_customer_population_or_age"}
    flow = kind == "유동"
    local = age_change(main_codes, panels[kind], ages, flow=flow)
    if not local["available"]:
        return {**local, "population": kind}
    key = (kind, tuple(ages))
    if key not in city_cache:
        old, new = (set(panels[kind][q]) for q in QUARTERS)
        city = age_change(sorted(old & new), panels[kind], ages, flow=flow)
        city["excluded_nonmatching_city_areas"] = sorted(old ^ new)
        city_cache[key] = city
    return {
        "available": True,
        "population": kind,
        "local": local,
        "city_matched_area_reference": city_cache[key],
        "proxy_population_used": False,
    }


def relative_change(evidence: dict) -> float | None:
    if not evidence.get("available"):
        return None
    local = evidence["local"]
    city = evidence["city_matched_area_reference"]
    if not city["available"]:
        return None
    old, new = (local["levels"][q] for q in QUARTERS)
    city_old, city_new = (city["levels"][q] for q in QUARTERS)
    if min(old, city_old, city_new) <= 0:
        return None
    return (new / old) / (city_new / city_old) - 1
