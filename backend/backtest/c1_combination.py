"""관측 경쟁 백분위와 관측 LQ의 결합만 바꾸고 다른 배점을 유지합니다."""

import math

MODES = ("control", "near_LQ75", "low_confidence_LQ75", "all_LQ75", "geometric", "harmonic")


def combine(profile_fraction: float, lq: float, kind: str, confidence: str, mode: str) -> dict:
    if (
        mode not in MODES
        or kind not in {"모임형", "근처형"}
        or type(profile_fraction) not in (int, float)
        or not math.isfinite(profile_fraction)
        or not 0 <= profile_fraction <= 1
        or type(lq) not in (int, float)
        or not math.isfinite(lq)
        or lq < 0
    ):
        raise ValueError("실제 경쟁 백분위·음이 아닌 LQ·고정 결합안이 필요합니다.")
    market = lq / (1 + lq)
    fraction = (profile_fraction + market) / 2
    if mode == "geometric":
        fraction = math.sqrt(profile_fraction * market)
    elif mode == "harmonic":
        denominator = profile_fraction + market
        fraction = 2 * profile_fraction * market / denominator if denominator else 0.0
    elif (
        mode == "all_LQ75"
        or (mode == "near_LQ75" and kind == "근처형")
        or (mode == "low_confidence_LQ75" and confidence == "low")
    ):
        fraction = 0.25 * profile_fraction + 0.75 * market
    return {
        "fraction": fraction,
        "profile_fraction": profile_fraction,
        "observed_LQ": lq,
        "LQ_fraction": market,
        "mode": mode,
        "represents_measured_success_probability": False,
    }
