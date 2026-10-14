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

음식점 경계표는 `python scripts/build_density_baseline.py` 로 다시 받아 갱신합니다.
51업종 경계표는 `--industries --emit`으로 density_percentiles.csv를 생성합니다.

⚠️ **서울 상권 분포다.** 서울 밖에서는 `None` 을 낸다.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Final

from app.industries.catalog import INDUSTRIES
from app.stats import percentile_rank

# 표본: 서울 상권 1,650곳 · 반경 500m · 소상공인 2026년 1분기 · 단위 개/km²
# 최소 0.0 · 중앙 411.3 · 최대 2,108.5
# 유형별 중앙값 — 골목상권 362.9 · 전통시장 513.1 · 발달상권 640.4 · 관광특구 855.6
BASELINE_SAMPLE_SIZE: Final = 1650
BASELINE_SCOPE: Final = "서울 상권 반경 500m"

# 5%p 간격 경계값(5% ~ 95%). scripts/build_density_baseline.py --emit 이 찍어준다.
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
    return _percentile(SEOUL_RESTAURANT_DENSITY_PERCENTILES, density)


def _percentile(bounds: tuple[float, ...], density: float) -> float | None:
    if not bounds or not math.isfinite(density) or density < 0:
        return None

    if density <= bounds[0]:
        return 0.0 if density < bounds[0] else _STEP
    if density >= bounds[-1]:
        return 100.0

    return round(
        percentile_rank(density, {int((i + 1) * _STEP): v for i, v in enumerate(bounds)}), 1
    )


# 원천: 소상공인시장진흥공단_상가(상권)정보_서울_202606.csv · 2026Q2
# 서울 상권 1,650개 중심 · 반경 500m · 개/km² · service-51 · 분할 누락 0
DENSITY_PERCENTILES_PATH: Final = (
    Path(__file__).resolve().parents[2] / "industries/data/density_percentiles.csv"
)


def load_density_percentiles(path: Path = DENSITY_PERCENTILES_PATH) -> dict[str, dict[int, float]]:
    """검토된 51업종 CSV를 읽고 누락·중복·잘못된 경계표를 거절합니다."""
    steps = range(5, 100, 5)
    result = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["industry_code", *(f"p{p}" for p in steps)]:
            raise ValueError("밀도 기준선 CSV 열이 일치하지 않습니다.")
        for row in reader:
            if None in row or None in row.values():
                raise ValueError("밀도 기준선 CSV 행의 열 개수가 다릅니다.")
            code = row["industry_code"]
            bounds = {p: float(row[f"p{p}"]) for p in steps}
            values = list(bounds.values())
            if (
                code in result
                or any(not math.isfinite(v) or v < 0 for v in values)
                or values != sorted(values)
            ):
                raise ValueError("밀도 기준선 CSV에 중복 업종·잘못된 경계값이 있습니다.")
            result[code] = bounds
    if result.keys() != INDUSTRIES.keys():
        raise ValueError("밀도 기준선 CSV는 51업종 전체가 필요합니다.")
    return result


SEOUL_INDUSTRY_DENSITY_PERCENTILES: Final[dict[str, dict[int, float]]] = load_density_percentiles()

# 중앙값이 사실상 점포 0인 업종은 안정적인 비교 분모가 없어 C1 unknown으로 남긴다.
C1_MIN_MEDIAN_DENSITY: Final = 0.01


def industry_percentile(code: str, density: float) -> float | None:
    """51업종 서울 밀도 백분위. 희소·미지원 업종과 잘못된 값은 None."""
    bounds = SEOUL_INDUSTRY_DENSITY_PERCENTILES.get(code)
    if bounds is None or bounds[50] < C1_MIN_MEDIAN_DENSITY:
        return None
    return _percentile(tuple(bounds[p] for p in range(5, 100, 5)), density)
