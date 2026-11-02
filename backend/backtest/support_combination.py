"""완전 원문 S2 추정과 관측 모집단 D3 보완의 고정 조합만 계산합니다."""

import math

MODES = {
    "control": (0, None),
    "S2_half": (0.5, None),
    "S2_full": (1, None),
    "S2_half_D3_quarter": (0.5, "D3_rank_quarter"),
    "S2_full_D3_quarter": (1, "D3_rank_quarter"),
    "S2_half_D3_half": (0.5, "D3_rank_half"),
    "S2_full_D3_half": (1, "D3_rank_half"),
}


def combine(original, statuses, support, corrections, mode):
    if mode not in MODES:
        raise ValueError("사전에 고정한 S2·D3 조합만 사용합니다.")
    strength, rank_mode = MODES[mode]
    fractions = dict(original)
    if strength and support is not None:
        if (
            support.get("kind") != "derived_full_period_estimate_not_new_observation"
            or support.get("source_status") != "unknown"
            or statuses["S2"] != "unknown"
        ):
            raise ValueError("검증된 완전 기간의 미확인 S2 추정만 혼합합니다.")
        value = support["fraction"]
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("S2 추정 기여는0~1이어야 합니다.")
        fractions["S2"] += strength * (value - original["S2"])
    correction = corrections.get(rank_mode, {"available": False})
    if rank_mode and correction["available"]:
        value = correction["fraction"]
        if (
            statuses["D3"] != "observed"
            or type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 <= value <= 1
        ):
            raise ValueError("같은 모집단 관측 D3의 검증된 분포 보완만 사용합니다.")
        fractions["D3"] = value
    return fractions
