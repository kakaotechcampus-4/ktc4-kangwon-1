"""연속 과거연도의 학교·주소를 대조하고 좌표 차이를 보수적으로 처리합니다."""

import math
import re
from collections import defaultdict

from app.geo import haversine_m
from backtest.cohort import address_key

GRADES = {"초등학교", "중학교", "고등학교", "특수학교", "각종학교", "고등기술학교"}


def stable_schools(rows: list[dict]) -> dict:
    groups = {"2024": defaultdict(list), "2025": defaultdict(list)}
    rejected = defaultdict(int)
    for row in rows:
        year = row.get("연도")
        if year not in groups:
            continue
        if (
            row.get("시도") not in {"서울특별시", "서울특별시교육청"}
            or row.get("학교급") not in GRADES
        ):
            rejected["outside_confirmed_school_subset"] += 1
            continue
        name, address = row.get("학교", "").strip(), row.get("주소", "").strip()
        try:
            lat, lon = float(row["위도"]), float(row["경도"])
        except (ValueError, TypeError, KeyError):
            rejected["invalid_coordinate"] += 1
            continue
        if not (
            name
            and address
            and math.isfinite(lat)
            and math.isfinite(lon)
            and 37.4 <= lat <= 37.8
            and 126.7 <= lon <= 127.3
        ):
            rejected["invalid_name_address_or_seoul_coordinate"] += 1
            continue
        key = (row.get("자치구"), row["학교급"], re.sub(r"\s+", "", name))
        groups[year][key].append(
            {
                "name": name,
                "address": address,
                "latitude": lat,
                "longitude": lon,
                "grade": row["학교급"],
                "district": row["자치구"],
            }
        )
    selected = []
    for key in sorted(set(groups["2024"]) | set(groups["2025"])):
        old, new = groups["2024"].get(key, []), groups["2025"].get(key, [])
        if len(old) != 1 or len(new) != 1:
            rejected["missing_or_ambiguous_between_years"] += 1
            continue
        a, b = old[0], new[0]
        old_address, new_address = address_key(a["address"]), address_key(b["address"])
        if old_address is None or old_address != new_address:
            rejected["changed_or_unparsed_building_address"] += 1
            continue
        selected.append(
            {
                **a,
                "years": [2024, 2025],
                "historical_subset": True,
                "matched_building_address_key": list(old_address),
                "coordinate_candidates": [
                    {"year": 2024, "latitude": a["latitude"], "longitude": a["longitude"]},
                    {"year": 2025, "latitude": b["latitude"], "longitude": b["longitude"]},
                ],
                "annual_coordinate_difference_m": haversine_m(
                    a["latitude"], a["longitude"], b["latitude"], b["longitude"]
                ),
                "coordinate_uncertainty_not_exact_same_point": True,
            }
        )
    return {
        "schools": selected,
        "rejected": dict(rejected),
        "school_subset_not_complete_SC4": True,
        "within_year_continuity_is_assumption": True,
    }


def distance_floor(profile: dict, site: dict, schools: list[dict]) -> dict:
    categories = profile.get("required_facilities", "").split(";")
    if "SC4" not in categories:
        return {"available": False, "reason": "school_not_required"}
    maximum = float(profile["max_distance_m"])
    if not math.isfinite(maximum) or maximum <= 0:
        raise ValueError("양수의 허용 거리가 필요합니다.")
    observed = sorted(
        (
            max(
                haversine_m(site["latitude"], site["longitude"], p["latitude"], p["longitude"])
                for p in r["coordinate_candidates"]
            ),
            i,
        )
        for i, r in enumerate(schools)
    )
    if not observed or observed[0][0] > maximum:
        return {"available": False, "reason": "no_attested_subset_school_within_limit_not_absence"}
    distance, index = observed[0]
    # 거리 소수점을 올려 보수적으로 등급 경계를 적용합니다.
    upper_distance = math.ceil(distance)
    t = upper_distance / maximum
    points = 2.5 * (4 - sum(t > edge for edge in (0.25, 0.5, 0.75, 1)))
    return {
        "available": True,
        "minimum_points": points,
        "distance_to_attested_subset_m": distance,
        "upper_bound_on_nearest_full_category_distance_m": upper_distance,
        "school": schools[index],
        "not_exact_nearest_full_category": True,
        "within_year_continuity_is_assumption": True,
        "distance_uses_worse_of_both_annual_coordinates": True,
    }


def apply_floor(detail: dict, components: dict, bound: dict) -> dict:
    if not bound["available"]:
        return {**detail, "historical_school_floor_applied": False}
    if (
        "SC4" not in components
        or any(v["status"] != "unknown" or v["points"] is not None for v in components.values())
        or detail["C4_source_status"] != "unknown"
        or detail["effective_C4_weight"] != 10
    ):
        raise ValueError("미확인 C4 10점에서만 별도 하한 근거를 반영합니다.")
    floor = bound["minimum_points"]
    if type(floor) not in (int, float) or not math.isfinite(floor) or not 0 <= floor <= 10:
        raise ValueError("시설 하한 점수는0~10점이어야 합니다.")
    estimate = detail["unknown_component_policy_points"]
    values = [max(estimate, floor) if c == "SC4" else estimate for c in components]
    contribution = sum(values) / len(values)
    raw = sum(detail["item_contributions"].values())
    value = 90 * (raw + contribution) / detail["applicable_weight"]
    return {
        **detail,
        "normalized": value,
        "effective_C4_contribution": contribution,
        "policy_aggregate_points": contribution,
        "historical_school_floor_applied": True,
        "historical_school_minimum_points": floor,
        "original_unknown_policy_aggregate_points": detail["policy_aggregate_points"],
        "C4_source_status": "unknown",
        "observed_aggregate_points": None,
        "source_status_and_unknown_weight_preserved": True,
    }
