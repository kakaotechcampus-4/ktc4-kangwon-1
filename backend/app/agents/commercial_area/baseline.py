"""서울 상권 분포에서 이 자리 음식점 밀도가 어디쯤인지.

## 왜 논문 임계값 대신 백분위인가

논문의 최적 밀도 임계값(발달 2.96 / 골목 4.31)을 못 쓰는 이유가 셋이다 —
단위가 확인 안 되고, 분모가 다르고(논문은 상권 폴리곤, 우리는 반경 원), 검증하려면
폐업 자료가 필요한데 그건 개폐업 파트다.

백분위는 추정이 아니라 **관측 분포 그 자체**라 틀릴 여지가 없다. 유동인구
`benchmark.scale_percentile` 과 같은 방식이라 세 에이전트가 같은 언어로 말하게 된다.

## 경계표는 어떻게 만들었나

서울 상권 1,650곳 중심좌표에 **우리와 똑같이 반경 500m 원을 씌워** 음식점을 셌다.
상권 폴리곤 면적(중앙값 약 0.07km²)을 쓰면 우리 분모(0.7854km²)와 10배 넘게 달라
어디를 찍든 최하위가 나오기 때문이다.

갱신은 `python examples/build_density_baseline.py` 로 다시 받아 이 상수를 바꾼다.

⚠️ **서울 상권 분포다.** 서울 밖에서는 `None` 을 낸다.
"""

from __future__ import annotations

from typing import Final

# 표본: 서울 상권 1,650곳 · 반경 500m · 소상공인 2026년 1분기 · 단위 개/km²
# 최소 0.0 · 중앙 411.3 · 최대 2,108.5
# 유형별 중앙값 — 골목상권 362.9 · 전통시장 513.1 · 발달상권 640.4 · 관광특구 855.6
BASELINE_SAMPLE_SIZE: Final = 1650
BASELINE_SCOPE: Final = "서울 상권 반경 500m"

# 5%p 간격 경계값(5% ~ 95%). examples/build_density_baseline.py --emit 이 찍어준다.
SEOUL_RESTAURANT_DENSITY_PERCENTILES: Final[tuple[float, ...]] = (
    98.04,  # 5%
    150.11,  # 10%
    198.63,  # 15%
    239.11,  # 20%
    273.75,  # 25%
    300.48,  # 30%
    327.22,  # 35%
    355.23,  # 40%
    384.52,  # 45%
    411.26,  # 50%
    444.3,  # 55%
    481.79,  # 60%
    528.2,  # 65%
    575.5,  # 70%
    628.66,  # 75%
    687.55,  # 80%
    767.32,  # 85%
    887.45,  # 90%
    1074.74,  # 95%
)

_STEP = 5.0


def seoul_percentile(density: float) -> float | None:
    """밀도가 서울 상권 분포의 몇 %인지. 경계표가 없으면 None.

    경계 사이는 선형 보간하고, 분포 밖은 0·100 으로 자른다.
    """
    bounds = SEOUL_RESTAURANT_DENSITY_PERCENTILES
    if not bounds or density < 0:
        return None

    if density <= bounds[0]:
        return 0.0 if density < bounds[0] else _STEP
    if density >= bounds[-1]:
        return 100.0

    for index in range(1, len(bounds)):
        low, high = bounds[index - 1], bounds[index]
        if density <= high:
            below = (index - 1 + 1) * _STEP
            if high == low:
                return round(below + _STEP, 1)
            share = (density - low) / (high - low)
            return round(below + share * _STEP, 1)
    return 100.0
