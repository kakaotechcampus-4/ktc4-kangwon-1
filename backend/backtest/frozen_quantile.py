"""개선 표본에서 찾은 30.2% 후보를 새 위치 검증용으로 고정합니다."""

import math

from app.agentic.scoring import WEIGHTS
from app.geo import haversine_m
from backtest.c1_quantile import profile_fraction
from backtest.frozen_rank import score_saved
from backtest.weight_selection import order_scores

CANDIDATE_ID = "city-c1-rank-D75-w35-30-15"
ITEM_WEIGHTS = {
    "D1": 10,
    "D2": 10,
    "D3": 10,
    "D4": 5,
    "C1": 30,
    "S1": 3.75,
    "S2": 3.75,
    "S3": 3.75,
    "S4": 3.75,
}


def fractions_for(row: dict, trace: dict, commercial: dict, reference: list[int]) -> dict:
    fractions = {}
    for name in ITEM_WEIGHTS:
        observed = trace["observed"][name]
        fraction = observed / WEIGHTS[name] if observed is not None else 0.0
        if name.startswith("D"):
            adjustment = trace["D_adjustment"]["items"].get(name)
            if adjustment:
                fraction += 0.75 * adjustment["weighted_delta"] / WEIGHTS[name]
        elif name == "C1":
            policy = trace["C1_policy"]
            if policy.get("applied"):
                if policy["mode"] != "lq_shrink5":
                    raise ValueError("고정 후보의 기존 C1 정책과 다릅니다.")
                fraction += policy["weighted_point_delta"] / 25
            original = row["items"]["C1"]
            if (
                original["status"] == "observed"
                and original.get("value") is not None
                and commercial.get("lq") is not None
            ):
                quantile = profile_fraction(
                    commercial["count"], reference, original["agglomeration"], "rank_direction"
                )
                fraction += 0.5 * (quantile["profile_fraction"] - original["grade"] / 4)
        else:
            fraction += trace["estimated_S"].get(name, 0.0) / WEIGHTS[name]
        if (
            not math.isfinite(fraction)
            or not -1e-12 <= fraction <= 1 + 1e-12
            or (trace["status"][name] == "n.a." and abs(fraction) > 1e-12)
        ):
            raise ValueError("고정 후보의 항목 기여가 원래 상태·배점 범위를 벗어났습니다.")
        fractions[name] = fraction
    return fractions


def score_candidate(saved: dict, calibration: dict, background: dict) -> dict:
    if background.get("reference_quarter") != "20252" or len(background.get("samples", [])) != 1650:
        raise ValueError("고정 분기의 서울 1,650개 상권 분포가 필요합니다.")
    baseline = score_saved(saved, calibration)
    site = saved["site"]
    area = saved["data"]["area_selection"]["area_code"]
    reference = [
        r
        for r in background["samples"]
        if r["area"] != area
        and haversine_m(site["latitude"], site["longitude"], r["latitude"], r["longitude"]) > 1000
    ]
    commercial = {r["code"]: r for r in saved["data"]["commercial_area"]["by_middle"]}
    values, details, ties = {}, {}, {}
    for row in saved["scores"]:
        code = row["code"]
        trace = baseline["details"][code]
        fractions = fractions_for(
            row, trace, commercial[code], sorted(r["counts"][code] for r in reference)
        )
        applicable = sum(w for name, w in ITEM_WEIGHTS.items() if trace["status"][name] != "n.a.")
        contributions = {
            name: ITEM_WEIGHTS[name] * fraction for name, fraction in fractions.items()
        }
        value = 80 * sum(contributions.values()) / applicable
        if not math.isfinite(value) or not -1e-10 <= value <= 80 + 1e-10:
            raise ValueError("고정 후보의 환산 점수가 유효하지 않습니다.")
        values[code] = value
        details[code] = {
            "original_status": trace["status"],
            "fractions": fractions,
            "weighted_contributions": contributions,
            "applicable": applicable,
            "S_estimates_are_not_observations": bool(trace["estimated_S"]),
        }
        ties[code] = {"coverage": row["coverage"], "adjustment": row["space"]["adjustment"]}
    return {
        "candidate_id": CANDIDATE_ID,
        "values": values,
        "order": order_scores(values, ties),
        "details": details,
        "reference_areas": [r["area"] for r in reference],
        "current80_order": baseline["orders"]["current80"],
        "retained_D75_order": baseline["orders"]["fixed_C1_D75"],
        "popular_order": baseline["orders"]["popular"],
    }
