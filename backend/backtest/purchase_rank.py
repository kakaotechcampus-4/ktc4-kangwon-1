"""정답 없는 같은 모집단의 분포에서 고객 가정의 상대 순위 차이만 보완합니다."""

import math
from bisect import bisect_left, bisect_right

from app.agents.floating_population.models import AGE_BANDS
from app.agents.floating_population.numeric import complete_sum


def distribution_for(codes, panel):
    found = sorted({c for c in codes if c in panel})
    if not found:
        return {"available": False, "reason": "no_observed_population_area"}
    total = complete_sum(panel[c].total for c in found)
    counts = {a: complete_sum(panel[c].by_age.get(a) for c in found) for a in AGE_BANDS}
    if total is None or total <= 0 or any(v is None for v in counts.values()):
        return {"available": False, "reason": "incomplete_population_denominator_or_age_bins"}
    return {
        "available": True,
        "shares": {a: round(v / total, 4) for a, v in counts.items()},
        "observed_area_codes": found,
    }


def correction(current, old_ratio, new_ratio, reference, strength):
    if (
        strength not in (0.25, 0.5)
        or type(current) not in (int, float)
        or not math.isfinite(current)
        or not 0 <= current <= 1
        or any(
            type(v) not in (int, float) or not math.isfinite(v) or v < 0
            for v in (old_ratio, new_ratio)
        )
        or any(len(row) != 2 for row in reference)
        or any(
            type(v) not in (int, float) or not math.isfinite(v) or v < 0
            for row in reference
            for v in row
        )
    ):
        raise ValueError("관측 적합도와 같은 모집단의 대응 참고 분포가 필요합니다.")
    if len(reference) < 20:
        return {"available": False, "reason": "insufficient_paired_reference"}
    old, new = (sorted(r[i] for r in reference) for i in (0, 1))

    def midrank(value, values):
        return (bisect_left(values, value) + bisect_right(values, value)) / (2 * len(values))

    old_q, new_q = midrank(old_ratio, old), midrank(new_ratio, new)
    delta = strength * (new_q - old_q)
    raw = current + delta
    return {
        "available": True,
        "fraction": min(1, max(0, raw)),
        "raw_fraction": raw,
        "clipped": not 0 <= raw <= 1,
        "delta": delta,
        "old_percentile_fraction": old_q,
        "new_percentile_fraction": new_q,
        "paired_reference_n": len(reference),
        "industry_constant_offset_or_exposure_quota": False,
    }
