"""서울 전체 상권 기준선 — 실측 상수.

"이 상권의 20대 비중 13%" 는 그 자체로는 높은지 낮은지 알 수 없다. 결정 에이전트가 점수를
계산하고 근거 문장을 쓰려면 **서울 평균 대비 상대값**이 필요하다. 그 기준선을 여기 박아둔다.

측정: 2026Q2 · 상권 1,648곳 · 총 1,321,890,016명 (2026-09-11, `tools-local/measure_baseline.py`)

**가중(합계) 기준이다** — 서울 전체 합계에서 비중을 낸 값이지, 상권별 비중의 평균이 아니다.
두 방식은 다른 값이 나온다(예: 20대 가중 0.180 vs 비가중 0.163). `classify.SEOUL_AVG` 가
가중 기준으로 만들어졌고 그 임계치가 실데이터로 검증돼 있어(길동 주거생활형·역삼1동 직장인형·
서교동 여가상업형 재현), 지표도 같은 기준으로
통일했다. 섞어 쓰면 지표와 유형 판정이 서로 다른 잣대를 쓰게 된다.

분기 데이터가 갱신되면 `tools-local/measure_baseline.py` 를 다시 돌려 이 상수를 갱신한다.
"""

from __future__ import annotations

from .models import TIME_BANDS

BASELINE_QUARTER = "20262"
BASELINE_LABEL = "서울 전체 상권 평균 (2026년 2분기 · 1,648곳)"

# 연령대별 비중 (가중). classify.SEOUL_AVG 와 같은 측정에서 나온 값이다.
AGE_SHARE_AVG = {
    "10": 0.1282,
    "20": 0.1797,
    "30": 0.1778,
    "40": 0.1660,
    "50": 0.1471,
    "60": 0.2013,
}

# 시간대별 "시간당" 비중 (가중). 구간 길이가 3~6시간으로 다르므로 반드시 시간당으로 비교한다.
TIME_PER_HOUR_SHARE_AVG = {
    "00_06": 0.1582,
    "06_11": 0.1614,
    "11_14": 0.1713,
    "14_17": 0.1730,
    "17_21": 0.1725,
    "21_24": 0.1637,
}

WEEKEND_TO_WEEKDAY_AVG = 0.9728

# 상권 1곳당 총 유동인구의 백분위 경계(명). 규모가 서울에서 어느 수준인지 환산하는 데 쓴다.
SCALE_PERCENTILES: dict[int, float] = {
    5: 38574.0,
    10: 67344.0,
    15: 113983.0,
    20: 165029.0,
    25: 212164.0,
    30: 262640.0,
    35: 329097.0,
    40: 392832.0,
    45: 461693.0,
    50: 538836.0,
    55: 610120.0,
    60: 706282.0,
    65: 820684.0,
    70: 948622.0,
    75: 1096199.0,
    80: 1270401.0,
    85: 1487086.0,
    90: 1825889.0,
    95: 2307516.0,
}


def index(value: float, average: float) -> float:
    """서울 평균 대비 배수. 1.0 이 평균, 1.2 면 평균의 1.2배."""
    if average <= 0:
        return 0.0
    return round(value / average, 3)


def scale_percentile(mean_per_area: float) -> int:
    """상권 1곳당 유동인구 → 서울 상권 중 백분위(0~100).

    에이전트는 반경 안 상권 여러 곳을 합산하므로, 분포(상권 1곳 단위)와 기준을 맞추려면
    **상권 수로 나눈 평균**을 넣어야 한다. 합계를 그대로 넣으면 상권이 많은 지역이 무조건
    상위로 나온다.
    """
    boundaries = sorted(SCALE_PERCENTILES.items())
    if mean_per_area <= boundaries[0][1]:
        return boundaries[0][0]
    prev_p, prev_v = boundaries[0]
    for p, v in boundaries[1:]:
        if mean_per_area <= v:
            # 두 경계 사이는 선형 보간
            span = v - prev_v
            frac = (mean_per_area - prev_v) / span if span else 0.0
            return int(round(prev_p + frac * (p - prev_p)))
        prev_p, prev_v = p, v
    return 99


def time_indices(time_per_hour_share: dict[str, float]) -> dict[str, float]:
    """시간대별 시간당 비중 → 서울 평균 대비 배수."""
    return {
        band: index(time_per_hour_share[band], TIME_PER_HOUR_SHARE_AVG[band])
        for band in TIME_BANDS
    }
