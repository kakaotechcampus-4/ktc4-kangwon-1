"""결측을 영값이나 부분 합계로 오인하지 않는 인구 계산입니다."""

from collections.abc import Iterable


def complete_sum(values: Iterable[float | None]) -> float | None:
    total = 0.0
    for value in values:
        if value is None:
            return None
        total += value
    return total


def rounded(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None else None


def ratio(value: float | None, denominator: float | None) -> float | None:
    if value is None or denominator is None:
        return None
    return value / denominator if denominator else 0.0
