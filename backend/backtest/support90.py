"""학교 연속성 가정 없이 고정한 S2·D3 두 후보를 새 위치에도 적용합니다."""

import math

from app.agentic.scoring import profiles
from app.geo import haversine_m
from app.industries.catalog import INDUSTRIES
from backtest.c4_policy import observe_components
from backtest.formula_support import apply_support
from backtest.formula_support import evidence_for as support_evidence
from backtest.historical90 import score_saved as historical_score
from backtest.historical_facility import apply_bounds
from backtest.purchase_profile import evidence_for as purchase_evidence
from backtest.purchase_rank import correction
from backtest.score90 import Score90Configuration, score90
from backtest.support_combination import combine
from backtest.weight_selection import order_scores

MODES = ("control", "S2_half", "S2_full_D3_quarter")
CONFIG = Score90Configuration(30, "equal")


def validate_reference(purchase, reference):
    if set(purchase) != set(INDUSTRIES):
        raise ValueError("원래51개 업종의 결제 프로필이 필요합니다.")
    if len(reference) != 1650 or len({r["area"] for r in reference}) != 1650:
        raise ValueError("중복 없는 서울1,650개 참고 위치가 필요합니다.")
    if any(set(r) != {"area", "latitude", "longitude", "ratios"} for r in reference):
        raise ValueError("참고 분포에는 정답 라벨과 추가 학습 정보를 넣지 않습니다.")
    if any(
        p["age"]["available"] and p["age"]["source_quarter"] != "20242" for p in purchase.values()
    ):
        raise ValueError("평가 시점보다 앞선 고정2024Q2 결제 프로필이 필요합니다.")
    for row in reference:
        if any(
            type(row[k]) not in (int, float) or not math.isfinite(row[k])
            for k in ("latitude", "longitude")
        ):
            raise ValueError("참고 위치의 실제 좌표가 필요합니다.")
        for code, pair in row["ratios"].items():
            if (
                code not in purchase
                or not purchase[code]["age"]["available"]
                or len(pair) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in pair)
            ):
                raise ValueError("같은 모집단의 수동·결제 적합도 쌍이 필요합니다.")


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
    medical,
    purchase,
    reference,
    city_day,
):
    validate_reference(purchase, reference)
    # 기존 계산에는 빈 학교 목록을 전달해 학교의 연도 내 영업·좌표 가정을 사용하지 않습니다.
    historical = historical_score(
        saved,
        calibration,
        background,
        areas,
        populations,
        population_reference,
        local_lifecycle,
        city_lifecycle,
        quarters,
        [],
        medical,
    )
    base = historical["details"]["balanced_S4"]
    catalog = profiles()
    rows = {r["code"]: r for r in saved["scores"]}
    area = saved["data"]["area_selection"]["area_code"]
    site = saved["site"]
    eligible = [
        row
        for row in reference
        if row["area"] != area
        and haversine_m(site["latitude"], site["longitude"], row["latitude"], row["longitude"])
        > 1000
    ]
    empty = {"data": {"queries": {}, "places": {}}}
    components = {c: observe_components(p, c, empty) for c, p in catalog.items()}
    supports, corrections, original = {}, {}, {}
    for code, before in base.items():
        original[code] = {n: p / CONFIG.weights[n] for n, p in before["item_contributions"].items()}
        e = (
            {"available": False, "reason": "partial_runtime_source"}
            if "business_lifecycle" in saved["data"].get("runtime_partial_sources", [])
            else support_evidence(
                code, quarters, local_lifecycle, city_lifecycle, calibration["lifecycle"].get(code)
            )
        )
        supports[code] = apply_support(
            original[code], rows[code]["items"], e, "S2_full_period_support"
        )["changes"].get("S2")
        evidence = purchase_evidence(
            catalog[code],
            saved["data"],
            rows[code]["items"],
            purchase[code],
            city_day,
            calibration["population"]["AGE_SHARE_AVG"],
        )["D3"]
        corrections[code] = {}
        if evidence["available"]:
            ratio = rows[code]["items"]["D3"]["value"]["r"]
            pairs = [r["ratios"][code] for r in eligible if code in r["ratios"]]
            corrections[code]["D3_rank_quarter"] = correction(
                original[code]["D3"], ratio, evidence["ratio"], pairs, 0.25
            )
    details, values = {}, {}
    for mode in MODES:
        details[mode] = {}
        for code, before in base.items():
            fractions = combine(
                original[code], before["source_status"], supports[code], corrections[code], mode
            )
            after = score90(
                fractions, before["source_status"], catalog[code], components[code], CONFIG
            )
            bounds = {k: v for k, v in historical["facility_bounds"][code].items() if k == "HP8"}
            after = apply_bounds(after, components[code], bounds)
            if (
                after["source_status"] != before["source_status"]
                or after["applicable_weight"] != before["applicable_weight"]
            ):
                raise ValueError("새 위치의 원문 상태나 미확인·미적용 분모가 바뀌었습니다.")
            if mode == "control" and not math.isclose(
                after["normalized"], before["normalized"], abs_tol=1e-10
            ):
                raise ValueError("새 위치에서 기존 의료기관 보완 후보가 재현되지 않습니다.")
            details[mode][code] = after
        values[mode] = {c: d["normalized"] for c, d in details[mode].items()}
    ties = {
        c: {"coverage": r["coverage"], "adjustment": r["space"]["adjustment"]}
        for c, r in rows.items()
    }
    orders = {m: order_scores(v, ties) for m, v in values.items()}
    orders["popular"] = historical["orders"]["popular"]
    return {
        "values": values,
        "details": details,
        "orders": orders,
        "S2_derived_support": supports,
        "D3_rank_corrections": corrections,
        "nominal_total": 90,
        "C4_max": 10,
        "current_map_observations_used": False,
        "school_annual_continuity_assumption_used": False,
        "medical_subset_not_complete_nearest_HP8": True,
        "published_point_in_time_vintages_unverified": True,
    }
