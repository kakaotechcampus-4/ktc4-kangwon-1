"""2025Q2 의료기관 좌표와 시설별 하한을 원래 미확인 상태와 분리합니다."""

import json
import math

from app.db.connection import readonly
from app.geo import haversine_m


def medical_sites(data):
    with readonly(data) as db:
        versions = db.execute(
            "SELECT v.*,f.columns_json FROM data_versions v JOIN source_fields f USING(version_id) "
            "WHERE v.source='stores' AND v.quarter='20252' AND v.state='active'"
        ).fetchall()
        if len(versions) != 1:
            raise ValueError("2025Q2 점포 버전이 하나여야 합니다.")
        version = dict(versions[0])
        columns = json.loads(version["columns_json"])
        index = columns.index("표준산업분류코드")
        sql = (
            "SELECT payload FROM stores WHERE version_id=? AND "
            f"(json_extract(payload,'$[{index}]') GLOB 'Q861*' "
            f"OR json_extract(payload,'$[{index}]') GLOB 'Q862*')"
        )
        records = [
            dict(zip(columns, json.loads(r[0]), strict=True))
            for r in db.execute(sql, (version["version_id"],))
        ]
    sites, rejected = [], []
    for row in records:
        try:
            lat, lon = float(row["위도"]), float(row["경도"])
        except (ValueError, TypeError, KeyError):
            rejected.append(row["상가업소번호"])
            continue
        if (
            not math.isfinite(lat)
            or not math.isfinite(lon)
            or not 37.4 <= lat <= 37.8
            or not 126.7 <= lon <= 127.3
        ):
            rejected.append(row["상가업소번호"])
            continue
        sites.append(
            {
                "store_id": row["상가업소번호"],
                "name": row["상호명"],
                "latitude": lat,
                "longitude": lon,
                "quarter": "20252",
                "standard_industry": row["표준산업분류코드"],
                "standard_industry_name": row["표준산업분류명"],
                "raw_address": row["도로명주소"],
                "source_kind": "frozen_20252_medical_store_subset",
            }
        )
    if len({r["store_id"] for r in sites}) != len(sites):
        raise ValueError("의료기관 점포의 원문 키가 중복됩니다.")
    return {
        "sites": sites,
        "invalid_coordinate_ids": rejected,
        "version": version,
        "subset_not_complete_HP8": True,
    }


def medical_floor(profile, site, medical):
    if "HP8" not in profile.get("required_facilities", "").split(";"):
        return {"available": False, "reason": "medical_facility_not_required"}
    maximum = float(profile["max_distance_m"])
    if not math.isfinite(maximum) or maximum <= 0:
        raise ValueError("유효한 허용 거리가 필요합니다.")
    pairs = [
        (haversine_m(site["latitude"], site["longitude"], r["latitude"], r["longitude"]), i)
        for i, r in enumerate(medical)
    ]
    if not pairs or min(pairs)[0] > maximum:
        return {"available": False, "reason": "no_attested_medical_subset_nearby_not_absence"}
    distance, index = min(pairs)
    upper = math.ceil(distance)
    points = 2.5 * (4 - sum(upper / maximum > edge for edge in (0.25, 0.5, 0.75, 1)))
    return {
        "available": True,
        "minimum_points": points,
        "facility": medical[index],
        "distance_to_attested_subset_m": distance,
        "upper_bound_on_nearest_full_category_distance_m": upper,
        "not_exact_nearest_full_category": True,
        "source_quarter": "20252",
    }


def apply_bounds(detail, components, bounds):
    usable = {k: v for k, v in bounds.items() if v["available"]}
    if not usable:
        return {**detail, "historical_facility_floor_applied": False}
    if (
        not set(usable) <= set(components)
        or detail["C4_source_status"] != "unknown"
        or detail["effective_C4_weight"] != 10
        or any(v["status"] != "unknown" or v["points"] is not None for v in components.values())
    ):
        raise ValueError("미확인 C4 10점에 같은 종류의 하한만 반영합니다.")
    if any(
        type(v["minimum_points"]) not in (int, float)
        or not math.isfinite(v["minimum_points"])
        or not 0 <= v["minimum_points"] <= 10
        for v in usable.values()
    ):
        raise ValueError("실제 자료에 근거한 하한 점수는0~10점이어야 합니다.")
    estimate = detail["unknown_component_policy_points"]
    points = [
        max(estimate, usable[k]["minimum_points"]) if k in usable else estimate for k in components
    ]
    contribution = sum(points) / len(points)
    normalized = (
        90
        * (sum(detail["item_contributions"].values()) + contribution)
        / detail["applicable_weight"]
    )
    return {
        **detail,
        "normalized": normalized,
        "effective_C4_contribution": contribution,
        "policy_aggregate_points": contribution,
        "historical_facility_floor_applied": True,
        "historical_facility_bounds": usable,
        "C4_source_status": "unknown",
        "observed_aggregate_points": None,
        "derived_from_unknown": True,
        "original_unknown_policy_aggregate_points": detail["policy_aggregate_points"],
        "source_status_and_unknown_weight_preserved": True,
    }
