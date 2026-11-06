"""백분위 경계 사이의 선형 보간을 공유합니다. 끝값·반올림은 호출자가 정합니다."""

from collections.abc import Mapping


def percentile_rank(value: float, thresholds: Mapping[int, float]) -> float:
    boundaries = sorted(thresholds.items())
    if not boundaries:
        raise ValueError("백분위 경계표가 필요합니다.")
    prev_p, prev_v = boundaries[0]
    if value <= prev_v:
        return float(prev_p)
    for p, v in boundaries[1:]:
        if value <= v:
            share = (value - prev_v) / (v - prev_v) if v != prev_v else 0.0
            return prev_p + share * (p - prev_p)
        prev_p, prev_v = p, v
    return float(prev_p)
