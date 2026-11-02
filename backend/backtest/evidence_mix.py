"""C1·S의 두 고정 배점을 단조 증가하는 제한된 방식으로 결합합니다."""

import numpy as np

MODES = ("mean", "half_max", "max")


def mixed_scores(
    demand_points: np.ndarray,
    demand_applicable: np.ndarray,
    competition_fraction: np.ndarray,
    survival_fraction: np.ndarray,
    mode: str,
) -> np.ndarray:
    arrays = (demand_points, demand_applicable, competition_fraction, survival_fraction)
    if (
        mode not in MODES
        or len({v.shape for v in arrays}) != 1
        or not all(np.isfinite(v).all() for v in arrays)
        or np.any(demand_applicable <= 0)
        or np.any(demand_applicable > 35)
        or np.any(demand_points < -1e-12)
        or np.any(demand_points > demand_applicable + 1e-12)
        or any(np.any((v < -1e-12) | (v > 1 + 1e-12)) for v in arrays[2:])
    ):
        raise ValueError("같은 후보의 유효한 D 관측·적용 배점과 C1·S 기여가 필요합니다.")
    denominator = demand_applicable + 45
    a = 80 * (demand_points + 30 * competition_fraction + 15 * survival_fraction) / denominator
    b = 80 * (demand_points + 15 * competition_fraction + 30 * survival_fraction) / denominator
    average = (a + b) / 2
    if mode == "mean":
        return average
    maximum = np.maximum(a, b)
    return maximum if mode == "max" else (average + maximum) / 2
