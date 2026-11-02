"""집적 무관 업종의 C1 정책 고정값을 분리해 시험하는 순수 계산입니다."""

import math

from app.agentic.scoring import valid

POLICY_MODES = ("keep", "not_applicable", "lq_shrink5", "lq_shrink10")


def apply_policy(
    base: dict, item: dict, code: str, data: dict, c1_weight: float, mode: str
) -> dict:
    if mode not in POLICY_MODES:
        raise ValueError("사전에 고정한 C1 정책 비교안이 필요합니다.")
    if mode == "keep" or not (
        item["status"] == "observed"
        and item.get("agglomeration") == "무관"
        and item.get("value") is None
    ):
        return {**base, "policy_change": {"applied": False}}
    if item["grade"] != 2 or not math.isclose(item["points"], 7.5):
        raise ValueError("C1 중간 등급 정책 고정값이 재현되지 않습니다.")
    if not valid(c1_weight) or c1_weight <= 0:
        raise ValueError("유효한 C1 배점이 필요합니다.")
    total = base["observed_points"] + base["estimated_points"]
    original_fixed = c1_weight / 2
    original_denominator = base["applicable"]
    detail = {
        "applied": True,
        "mode": mode,
        "source_basis": "profile_fixed",
        "source_points": 7.5,
        "source_status_preserved": True,
        "new_is_measured_local_fit": False,
    }
    if mode == "not_applicable":
        denominator = original_denominator - c1_weight
        total -= original_fixed
        detail.update(
            {
                "interpretation": "집적 무관을 미적용으로 해석하는 실험 가정",
                "experimental_not_applicable_weight": c1_weight,
            }
        )
    else:
        if (
            not data.get("commercial_collection_complete")
            or code in data.get("commercial_split_missing", [])
            or data.get("commercial_area", {}).get("radius_m") != 500
            or data.get("comparison_radius_m") != 2000
        ):
            return {
                **base,
                "policy_change": {"applied": False, "reason": "unverified_market_source"},
            }
        commercial = next(
            (v for v in data["commercial_area"]["by_middle"] if v["code"] == code), None
        )
        if commercial is not None and commercial.get("lq") is None:
            return {
                **base,
                "policy_change": {"applied": False, "reason": "comparison_LQ_unavailable"},
            }
        if (
            commercial is None
            or type(commercial.get("count")) is not int
            or commercial["count"] < 0
            or not valid(commercial.get("lq"))
            or commercial["lq"] < 0
        ):
            raise ValueError("완전한 주변 점포 수와 유효한 관측 LQ가 필요합니다.")
        count, lq = commercial["count"], commercial["lq"]
        prior = 5 if mode == "lq_shrink5" else 10
        reliability = count / (count + prior)
        grade_lq = 4 * lq / (1 + lq)
        grade = 2 + reliability * (grade_lq - 2)
        delta = c1_weight * (grade - 2) / 4
        total += delta
        denominator = original_denominator
        detail.update(
            {
                "count": count,
                "observed_lq": lq,
                "prior_count": prior,
                "reliability": reliability,
                "grade_from_lq": grade_lq,
                "estimated_grade": grade,
                "weighted_point_delta": delta,
                "interpretation": "정책 중간값에 실제 LQ를 관측량으로 할인해 결합한 추정",
            }
        )
    if denominator <= 0 or total < -1e-10:
        raise ValueError("C1 정책 가정 후 적용 배점·총점이 유효하지 않습니다.")
    return {
        **base,
        "normalized": 80 * total / denominator,
        "policy_adjusted_points": total,
        "policy_adjusted_applicable": denominator,
        "policy_change": detail,
    }
