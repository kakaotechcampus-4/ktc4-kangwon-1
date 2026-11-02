"""S4 실제0건 보완과 C1·S 가변 배점의 균형 후보를 새 위치용으로 고정합니다."""

import math

import numpy as np

from app.agentic.scoring import WEIGHTS
from app.agents.business_lifecycle.client import get_recent_quarters
from backtest.evidence_mix import mixed_scores
from backtest.frozen_rank import score_saved
from backtest.s4_difference import changed_fraction, difference_evidence
from backtest.weight_selection import order_scores

CANDIDATE_ID = "fixed-c1-D75-S4zero-flex-max"


def components_for(
    code: str, trace: dict, raw_local: dict, raw_city: dict, *, partial: bool
) -> dict:
    demand = sum(trace["observed"][name] or 0 for name in ("D1", "D2", "D3", "D4"))
    demand += 0.75 * trace["D_adjustment"]["weighted_delta"]
    applicable = sum(
        WEIGHTS[name] for name in ("D1", "D2", "D3", "D4") if trace["status"][name] != "n.a."
    )
    competition = (trace["observed"]["C1"] or 0) / 15
    policy = trace["C1_policy"]
    if policy.get("applied"):
        if policy["mode"] != "lq_shrink5":
            raise ValueError("고정한 C1 정책과 다릅니다.")
        competition += policy["weighted_point_delta"] / 25
    survival = {
        name: ((trace["observed"][name] or 0) + trace["estimated_S"].get(name, 0)) / 7.5
        for name in ("S1", "S2", "S3", "S4")
    }
    evidence = (
        {"available": False, "reason": "runtime_partial_source"}
        if partial
        else difference_evidence(code, get_recent_quarters("20252", 12), raw_local, raw_city)
    )
    repair = changed_fraction(trace["status"]["S4"], evidence, "zero_old_only")
    if repair is not None:
        survival["S4"] = repair
    return {
        "D_points": demand,
        "D_applicable": applicable,
        "C1_fraction": competition,
        "S_fractions": survival,
        "S_fraction": sum(survival.values()) / 4,
        "S4_derived_repair": evidence if repair is not None else None,
        "source_status": dict(trace["status"]),
        "C1_policy_is_not_measured_customer_fit": bool(policy.get("applied")),
    }


def score_balanced(saved: dict, calibration: dict, raw_local: dict, raw_city: dict) -> dict:
    baseline = score_saved(saved, calibration)
    values, details, ties = {}, {}, {}
    partial = "business_lifecycle" in saved["data"]["runtime_partial_sources"]
    for row in saved["scores"]:
        code = row["code"]
        trace = baseline["details"][code]
        if any(trace["status"][name] == "n.a." for name in ("C1", "S1", "S2", "S3", "S4")):
            raise ValueError("고정 후보는 C1·S 적용 배점을 유지해야 합니다.")
        features = components_for(code, trace, raw_local, raw_city, partial=partial)
        values[code] = float(
            mixed_scores(
                *(
                    np.asarray(features[k])
                    for k in ("D_points", "D_applicable", "C1_fraction", "S_fraction")
                ),
                "max",
            )
        )
        if not math.isfinite(values[code]):
            raise ValueError("고정한 가변 배점 점수가 유효하지 않습니다.")
        details[code] = features
        ties[code] = {"coverage": row["coverage"], "adjustment": row["space"]["adjustment"]}
    return {
        "candidate_id": CANDIDATE_ID,
        "values": values,
        "order": order_scores(values, ties),
        "details": details,
        "retained_D75_order": baseline["orders"]["fixed_C1_D75"],
        "current80_order": baseline["orders"]["current80"],
        "popular_order": baseline["orders"]["popular"],
    }
