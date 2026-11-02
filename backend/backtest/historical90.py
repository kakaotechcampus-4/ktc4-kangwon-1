"""현재 지도 관측 없이 고정된 두90점 후보를 새 위치에서도 같은 식으로 계산합니다."""

import math

from app.agentic.scoring import profiles
from app.geo import haversine_m
from backtest.c1_combination import combine
from backtest.c1_quantile import profile_fraction
from backtest.historical_facility import apply_bounds, medical_floor
from backtest.historical_school import distance_floor
from backtest.holdout90 import calculate
from backtest.s4_difference import changed_fraction, difference_evidence
from backtest.score90 import Score90Configuration, score90
from backtest.weight_selection import order_scores

CONFIG = Score90Configuration(30, "equal")


def score_saved(
    saved,
    calibration,
    background,
    areas,
    populations,
    population_reference,
    local_lifecycle,
    city_lifecycle,
    quarters,
    schools,
    medical,
):
    catalog = profiles()
    current = calculate(saved, calibration, background, areas, populations, population_reference)
    base = current["details"]["customer_half_actual90"]
    data, site = saved["data"], saved["site"]
    area = data["area_selection"]["area_code"]
    reference = [
        r
        for r in background["samples"]
        if r["area"] != area
        and haversine_m(site["latitude"], site["longitude"], r["latitude"], r["longitude"]) > 1000
    ]
    rows = {r["code"]: r for r in saved["scores"]}
    commercial = {r["code"]: r for r in data["commercial_area"]["by_middle"]}
    complete = (
        data.get("commercial_collection_complete")
        and not set(data.get("runtime_partial_sources", []))
        & {"commercial_area", "floating_population"}
        and data["commercial_area"].get("radius_m") == 500
        and data.get("comparison_radius_m") == 2000
    )
    bounds, bound_cache, repairs = {}, {}, {}
    for code, p in catalog.items():
        local = {}
        for category in p.get("required_facilities", "").split(";"):
            if category not in {"SC4", "HP8"}:
                continue
            key = category, float(p["max_distance_m"])
            if key not in bound_cache:
                bound_cache[key] = (
                    distance_floor(p, site, schools)
                    if category == "SC4"
                    else medical_floor(p, site, medical)
                )
            local[category] = bound_cache[key]
        bounds[code] = local
        repairs[code] = difference_evidence(code, quarters, local_lifecycle, city_lifecycle)
    details, values = {}, {}
    for method in ("accuracy", "balanced_S4"):
        details[method] = {}
        for code, old in base.items():
            fractions = {n: p / CONFIG.weights[n] for n, p in old["item_contributions"].items()}
            if method == "balanced_S4":
                item, local = rows[code]["items"]["C1"], commercial[code]
                if (
                    complete
                    and code not in data.get("commercial_split_missing", [])
                    and item["status"] == "observed"
                    and item.get("value") is not None
                    and local.get("lq") is not None
                ):
                    q = profile_fraction(
                        local["count"],
                        sorted(r["counts"][code] for r in reference),
                        item["agglomeration"],
                        "rank_direction",
                    )
                    args = (
                        q["profile_fraction"],
                        local["lq"],
                        item["agglomeration"],
                        catalog[code]["agglomeration_confidence"],
                    )
                    if not math.isclose(
                        combine(*args, "control")["fraction"], fractions["C1"], abs_tol=1e-10
                    ):
                        raise ValueError("기존 C1의 관측 결합식이 재현되지 않습니다.")
                    fractions["C1"] = combine(*args, "near_LQ75")["fraction"]
                repair = changed_fraction(
                    old["source_status"]["S4"], repairs[code], "zero_old_only"
                )
                if repair is not None:
                    if not math.isclose(fractions["S4"], 0, abs_tol=1e-10):
                        raise ValueError("과거 폐업0의 미확인 S4에 이미 기여가 있습니다.")
                    fractions["S4"] = repair
            scored = score90(
                fractions,
                old["source_status"],
                catalog[code],
                current["C4_components"][code],
                CONFIG,
            )
            details[method][code] = apply_bounds(
                scored, current["C4_components"][code], bounds[code]
            )
        values[method] = {c: d["normalized"] for c, d in details[method].items()}
    ties = {
        c: {"coverage": r["coverage"], "adjustment": r["space"]["adjustment"]}
        for c, r in rows.items()
    }
    orders = {m: order_scores(v, ties) for m, v in values.items()}
    orders["popular"] = sorted(commercial, key=lambda c: (-commercial[c]["count"], c))
    return {
        "values": values,
        "details": details,
        "orders": orders,
        "facility_bounds": bounds,
        "S4_repair_evidence": repairs,
        "nominal_total": 90,
        "C4_max": 10,
        "current_map_observations_used": False,
        "school_annual_continuity_and_coordinate_interval_are_assumptions": True,
    }
