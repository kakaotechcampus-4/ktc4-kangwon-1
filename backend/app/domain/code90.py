"""선택한 S2_half의 순수 계산. 원래 관측 등급·fact와 추정 기여를 분리합니다."""

from bisect import bisect_left, bisect_right
from copy import deepcopy
from statistics import mean

from app.domain.population import quarter_days
from app.domain.quarters import get_recent_quarters
from app.domain.stats import calculate_rate

METHOD = "S2_half-v1"
WEIGHTS = {
    "D1": 10,
    "D2": 10,
    "D3": 10,
    "D4": 5,
    "C1": 30,
    "S1": 3.75,
    "S2": 3.75,
    "S3": 3.75,
    "S4": 3.75,
    "C4": 10,
}
RATIO_EDGES = (0.8, 0.95, 1.05, 1.2)
TREND_EDGES = (-10, -3, 3, 10)


def smooth(value, edges):
    knots = (edges[0] - (edges[1] - edges[0]) / 2, *edges, edges[-1] + (edges[-1] - edges[-2]) / 2)
    grades = (0, 0.5, 1.5, 2.5, 3.5, 4)
    if value <= knots[0]:
        return 0.0
    if value >= knots[-1]:
        return 4.0
    hi = bisect_right(knots, value)
    part = (value - knots[hi - 1]) / (knots[hi] - knots[hi - 1])
    return grades[hi - 1] + part * (grades[hi] - grades[hi - 1])


def demand_fraction(name, item):
    original = item["grade"] / 4
    value = item.get("value")
    if name == "D1":
        if not isinstance(value, dict):
            return original
        grade = min(smooth(value["r"], RATIO_EDGES), smooth(value["p"], (20, 40, 60, 80)))
    else:
        if name == "D3":
            value = value["r"]
        if name == "D4":
            value *= 100
        grade = smooth(value, TREND_EDGES if name == "D4" else RATIO_EDGES)
    return 0.25 * original + 0.75 * grade / 4


def trend_fraction(change):
    value = 100 * change
    return (0.25 * bisect_right(TREND_EDGES, value) + 0.75 * smooth(value, TREND_EDGES)) / 4


def stability_fraction(name, ratio):
    if name == "S2":
        z = ratio - 1
        return 0.5 + 0.5 * z / (1 + abs(z))
    return 1 / (1 + ratio)


def customer_change(profile, data):
    """같은 모집단·연령·상권 집합의 실제 전년 값만 사용합니다."""
    kind = profile.get("target_population")
    ages = [age for age in profile.get("target_age_bands", "").split(";") if age]
    current = data.get("floating_population", {}).get("period_code")
    if not current or not ages:
        return None
    previous = str(int(current[:4]) - 1) + current[-1]
    history = data.get("score90_customer_population", {}).get(kind, {})
    panels = [history.get(q, {}) for q in (previous, current)]
    if not panels[0] or set(panels[0]) != set(panels[1]):
        return None
    levels = []
    for quarter, panel in zip((previous, current), panels, strict=True):
        values = [row.get(age) for row in panel.values() for age in ages]
        if any(value is None for value in values):
            return None
        total = sum(values)
        levels.append(round(total / quarter_days(quarter), 1) if kind == "유동" else total)
    return round((levels[1] - levels[0]) / levels[0], 4) if levels[0] > 0 else None


def lifecycle_counts(code, data, baseline, quarter):
    """불완전 원문·0 보충·다른 기간에는 소량 관측 보완을 적용하지 않습니다."""
    if (
        not baseline
        or not baseline.get("data_complete")
        or baseline.get("zero_filled_sources") != 0
    ):
        return None
    if "business_lifecycle" in data.get("runtime_partial_sources", []):
        return None
    life = data.get("business_lifecycle", {})
    details = data.get("lifecycle_quarterly", {})
    if life.get("metadata") != {"base_quarter": quarter, "quarter_count": 12}:
        return None
    if details.get("quarters") != get_recent_quarters(quarter, 12):
        return None
    row = next((r for r in life.get("industries", []) if r["industry_id"] == code), {})
    detail = next((r for r in details.get("industries", []) if r["industry_id"] == code), {})
    if (
        not row.get("data_complete")
        or row.get("zero_filled_sources") != 0
        or detail.get("zero_filled_sources") != 0
    ):
        return None
    columns = [detail.get(k, []) for k in ("store_counts", "opened_counts", "closed_counts")]
    if any(len(col) != 12 or any(type(v) is not int or v < 0 for v in col) for col in columns):
        return None
    stores, opened, closed = columns
    total, old, recent = sum(stores), sum(stores[:4]), sum(stores[-4:])
    metrics = {
        "avg_store_count": total / 12,
        "recent_year_close_rate": calculate_rate(sum(closed[-4:]), recent),
        "oldest_year_close_rate": calculate_rate(sum(closed[:4]), old),
        "net_change_rate": calculate_rate(sum(opened) - sum(closed), total),
        "turnover_rate": calculate_rate(sum(opened) + sum(closed), total),
    }
    for field, value in metrics.items():
        saved = row.get("metrics", {}).get(field)
        if value != saved and not (field == "avg_store_count" and round(value, 2) == saved):
            raise ValueError("개폐업 분기 건수와 저장 지표가 다릅니다: " + field)
    return metrics | {
        "exposure": total,
        "old_exposure": old,
        "recent_exposure": recent,
        "old_closed": sum(closed[:4]),
        "recent_closed": sum(closed[-4:]),
    }


def stability_ratio(name, local, city):
    if name in {"S1", "S3"}:
        key = "recent_year_close_rate" if name == "S1" else "turnover_rate"
        return local[key] / city[key] if local[key] is not None and city[key] > 0 else None
    if name == "S2":
        return (
            1 + (local["net_change_rate"] - city["net_change_rate"]) / city["turnover_rate"]
            if local["net_change_rate"] is not None and city["turnover_rate"] > 0
            else None
        )
    recent, old = local["recent_year_close_rate"], local["oldest_year_close_rate"]
    base_recent, base_old = city["recent_year_close_rate"], city["oldest_year_close_rate"]
    return (
        (recent / old) / (base_recent / base_old)
        if recent is not None and old is not None and min(old, base_recent, base_old) > 0
        else None
    )


def stability_estimate(name, item, local, city):
    if not local or item["status"] != "unknown":
        return 0.0, "unavailable"
    exposure = local["exposure"]
    window = min(local["old_exposure"], local["recent_exposure"])
    effective = min(exposure, window) if name in {"S2", "S4"} else exposure
    ratio = stability_ratio(name, local, city)
    fraction = 0.0
    reason = "unavailable"
    if (
        (exposure < 40 or (name in {"S2", "S4"} and window < 40))
        and 0 < effective <= 40
        and ratio is not None
    ):
        fraction = stability_fraction(name, ratio) * (effective / 40) ** 2
        reason = "complete_low_exposure_quadratic"
    # 전체 기간이 충분한 S2만 기존 할인 추정과 전체 기간 계산의 중간값을 사용합니다.
    if (
        name == "S2"
        and item.get("reason") == "과거·최근 각각 노출량 부족"
        and exposure >= 40
        and window < 40
        and ratio is not None
    ):
        fraction = (fraction + stability_fraction(name, ratio)) / 2
        reason = "complete_full_period_S2_half"
    # 실제 과거 폐업 0건은 원문 누락과 구분합니다. 충분한 두 비교창에서만 변화량을 씁니다.
    if name == "S4" and local["old_closed"] == 0 and window >= 40:
        city_old = city.get("oldest_year_close_rate_exact", city["oldest_year_close_rate"])
        city_recent = city.get("recent_year_close_rate_exact", city["recent_year_close_rate"])
        scale = (city_old + city_recent) / 200
        if scale > 0:
            difference = (
                local["recent_closed"] / local["recent_exposure"] - (city_recent - city_old) / 100
            )
            z = difference / scale
            fraction, reason = 0.5 - 0.5 * z / (1 + abs(z)), "complete_zero_old_closures"
    return fraction, reason


def competition_fraction(item, commercial, reference, complete):
    original = item["grade"] / 4
    lq = commercial.get("lq")
    if not complete or lq is None or lq < 0:
        return original, "original_observation"
    market = lq / (1 + lq)
    count = commercial["count"]
    kind = item.get("agglomeration")
    if kind == "무관":
        return 0.5 + count / (count + 5) * (market - 0.5), "profile_fixed_LQ_shrink5"
    if item.get("value") is None or len(reference) < 20:
        return (original + market) / 2, "observed_LQ_half_without_reference"
    quantile = (bisect_left(reference, count) + bisect_right(reference, count)) / (
        2 * len(reference)
    )
    profile = 1 - quantile if kind == "근처형" else quantile
    return (
        (0.25 * profile + 0.75 * market) if kind == "근처형" else (profile + market) / 2
    ), "city_count_rank_and_LQ"


def observed_fraction(name, item, profile, data, code, commercial, reference, complete):
    if name.startswith("D"):
        fraction = demand_fraction(name, item)
        change = data.get("score90_customer_trends", {}).get(code)
        if change is None:
            change = customer_change(profile, data)
        if name == "D4" and change is not None:
            return (fraction + trend_fraction(change)) / 2, "matched_customer_yoy_half"
        return fraction, "D75_continuous"
    if name.startswith("S"):
        return stability_fraction(name, item["value"]), "S_ratio_continuous"
    return competition_fraction(item, commercial, reference, complete)


def calculate(
    items,
    profile,
    code,
    data,
    *,
    city,
    quarter,
    reference=(),
    components=None,
    facility_floors=None,
):
    """관측 점수는 보존하고 항목별 새 배점 기여만 별도 메타데이터에 담습니다."""
    out = deepcopy(items)
    local = lifecycle_counts(code, data, city, quarter)
    commercial = next(
        (r for r in data.get("commercial_area", {}).get("by_middle", []) if r["code"] == code), {}
    )
    complete = (
        data.get("commercial_collection_complete")
        and code not in data.get("commercial_split_missing", [])
        and data.get("commercial_area", {}).get("radius_m") == 500
        and data.get("comparison_radius_m") == 2000
        and "commercial_area" not in data.get("runtime_partial_sources", [])
    )
    for name, weight in WEIGHTS.items():
        if name == "C4":
            continue
        item = items[name]
        fraction, reason = 0.0, "unavailable"
        if item["status"] == "observed":
            fraction, reason = observed_fraction(
                name, item, profile, data, code, commercial, reference, complete
            )
        elif name.startswith("S"):
            fraction, reason = stability_estimate(name, item, local, city)
        if item["status"] == "n.a.":
            fraction, reason = 0.0, "not_applicable"
        out[name]["scoring"] = {
            "method": METHOD,
            "weight": weight,
            "points": weight * fraction,
            "basis": reason,
            "estimated": item["status"] == "unknown" and fraction > 0,
        }
    common = [out[n] for n in WEIGHTS if n != "C4"]
    applicable = sum(v["scoring"]["weight"] for v in common if v["status"] != "n.a.")
    total = sum(v["scoring"]["points"] for v in common)
    estimate = 10 * max(0.0, total / applicable - 0.25) if applicable else 0.0
    parts = components or {}
    points = []
    for category, component in parts.items():
        point = component["points"] if component["status"] == "observed" else estimate
        if component["status"] == "unknown":
            point = max(point, (facility_floors or {}).get(category, 0.0))
        points.append(point)
    c4 = items["C4"]
    c4_points = (mean(points) if points else estimate) if c4["status"] != "n.a." else 0.0
    out["C4"]["scoring"] = {
        "method": METHOD,
        "weight": 10,
        "points": c4_points,
        "basis": "facility_component_mean" if parts else "facility_unverified_one_grade_discount",
        "estimated": any(v["status"] == "unknown" for v in parts.values())
        or c4["status"] == "unknown",
    }
    return out


def summary(items):
    # JSON 저장이 문항 키 순서를 바꿔도 실수 합산·동점 순위를 동일하게 유지합니다.
    applicable = sum(
        items[name]["scoring"]["weight"] for name in WEIGHTS if items[name]["status"] != "n.a."
    )
    raw = sum(items[name]["scoring"]["points"] for name in WEIGHTS)
    code = min(90.0, max(0.0, 90 * raw / applicable)) if applicable else 0.0
    return {
        "method": METHOD,
        "code_points": code,
        "ranking_points": code + (items["L"]["points"] or 0),
        "applicable_weight": applicable,
        "raw_points": raw,
        "estimated_points": sum(
            items[name]["scoring"]["points"]
            for name in WEIGHTS
            if items[name]["scoring"]["estimated"]
        ),
    }
