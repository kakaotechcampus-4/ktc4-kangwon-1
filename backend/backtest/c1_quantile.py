"""밀도 중앙값 배율 대신 실제 참고 분포의 상대 위치를 비교합니다."""

from bisect import bisect_left, bisect_right

MODES = ("rank_direction", "rank_hump_near")
MIN_REFERENCE_N = 20


def profile_fraction(count: int, reference: list[int], kind: str, mode: str) -> dict:
    if (
        type(count) is not int
        or count < 0
        or len(reference) < MIN_REFERENCE_N
        or any(type(v) is not int or v < 0 for v in reference)
        or reference != sorted(reference)
        or kind not in {"모임형", "근처형"}
        or mode not in MODES
    ):
        raise ValueError("관측 점포 수와 정렬된 충분한 과거 분포·고정 비교안이 필요합니다.")
    # 같은 수의 점포는 같은 중간 백분위를 받습니다. 0개 관측도 임의로 분산하지 않습니다.
    fraction = (bisect_left(reference, count) + bisect_right(reference, count)) / (
        2 * len(reference)
    )
    if kind == "모임형":
        score = fraction
    elif mode == "rank_direction":
        score = 1 - fraction
    else:
        score = 4 * fraction * (1 - fraction)
    return {"quantile": fraction, "profile_fraction": score, "reference_n": len(reference)}
