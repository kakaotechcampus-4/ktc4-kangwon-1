"""숫자를 풀어 쓴 해석 문장 (`data.interpretation`).

**문장은 코드가 규칙으로 만든다 — LLM 을 쓰지 않는다.** 같은 입력이면 항상 같은 문장이고,
문장 속 숫자는 `data` 에 실린 값을 읽기 좋게 소수 둘째 자리까지만 옮긴다(원값은 `path` 에).
결정 에이전트가 단위·기준을 다시 추론하지 않고 핵심을 먼저 읽게 하려는 것이며, 각 문장의
`path` 를 그대로 `evidence.path` 로 쓸 수 있다.

업종을 추천하거나 원인을 단정하는 문장은 만들지 않는다 — 그건 결정 에이전트의 몫이다.
"""

from __future__ import annotations

from .models import AGE_BANDS
from .schemas import Finding, FloatingPopulationData

# 서울 평균 대비 이 배수를 넘거나 밑돌 때만 "두드러진다" 고 쓴다.
HIGH = 1.1
LOW = 0.9

TIME_LABELS = {
    "00_06": "새벽(0~6시)",
    "06_11": "오전(6~11시)",
    "11_14": "점심(11~14시)",
    "14_17": "오후(14~17시)",
    "17_21": "저녁(17~21시)",
    "21_24": "밤(21~24시)",
}
AGE_LABELS = {a: f"{a}대" for a in AGE_BANDS} | {"60": "60대 이상"}
LEVEL_LABELS = {"high": "높음", "medium": "보통", "low": "낮음"}


def interpret(data: FloatingPopulationData) -> list[Finding]:
    findings = [
        Finding(
            text=f"유동인구 연령·요일 분포로 보면 {data.type.label}이다(직업 자료가 아닌 추정).",
            path="/type/label",
        ),
        _scale(data),
        _peak(
            data.benchmark.time_per_hour_index,
            TIME_LABELS,
            "시간당 통행 비중",
            "/benchmark/time_per_hour_index",
        ),
        _peak(data.benchmark.age_index, AGE_LABELS, "유동인구 비중", "/benchmark/age_index"),
    ]
    weekend = data.benchmark.weekend_index
    if weekend is not None and (weekend >= HIGH or weekend <= LOW):
        tone = "주말에 상대적으로 붐빈다" if weekend >= HIGH else "주중 중심이다"
        findings.append(
            Finding(
                text=f"주말/주중 통행 비가 서울 평균의 {weekend:.2f}배로 {tone}.",
                path="/benchmark/weekend_index",
            )
        )
    trend = data.trend
    if trend is not None:
        # 기본 4개 분기에서는 전년 동기가 없어 yoy_change 가 늘 null 이다 → 직전 분기로 물러선다.
        if trend.yoy_change is not None:
            change, basis, path = trend.yoy_change, "전년 같은 분기", "/trend/yoy_change"
        elif trend.qoq_change is not None:
            change, basis, path = trend.qoq_change, "직전 분기", "/trend/qoq_change"
        else:
            change = None
        if change is not None:
            findings.append(
                Finding(
                    text=f"하루 유동인구는 {basis}보다 {change:+.1%} ({trend.direction}).",
                    path=path,
                )
            )
    summary = data.population_summary
    # index 가 있으면 ratio·seoul ratio 도 있다(summary_block).
    if summary is not None and summary.worker_to_resident_index is not None:
        findings.append(
            Finding(
                text=(
                    f"직장인구가 주거인구의 {summary.worker_to_resident_ratio:.2f}배로 서울 평균"
                    f"({summary.seoul_worker_to_resident_ratio:.2f}배)의 "
                    f"{summary.worker_to_resident_index:.2f}배다 — {summary.composition}."
                ),
                path="/population_summary/worker_to_resident_index",
            )
        )
    resident = data.resident
    # 가구당 인원 지수가 있으면 가구당 인원도 있다(_benchmark).
    if resident is not None and resident.benchmark.persons_per_household_index is not None:
        household_index = resident.benchmark.persons_per_household_index
        if household_index <= LOW:
            tone = "1인 가구가 많은 편이다"
        elif household_index >= HIGH:
            tone = "가족 단위 가구가 많은 편이다"
        else:
            tone = "서울 평균과 비슷하다"
        findings.append(
            Finding(
                text=(
                    f"주거인구는 가구당 {resident.persons_per_household:.2f}명으로 서울 평균의 "
                    f"{household_index:.2f}배 — {tone}."
                ),
                path="/resident/benchmark/persons_per_household_index",
            )
        )
    if data.reliability.level != "high":
        findings.append(
            Finding(
                text=(
                    f"자료가 있는 상권이 {data.reliability.covered_trade_areas}곳이라 "
                    f"신뢰도는 {LEVEL_LABELS[data.reliability.level]}이다."
                ),
                path="/reliability/level",
            )
        )
    return [finding for finding in findings if finding is not None]


def _scale(data: FloatingPopulationData) -> Finding | None:
    p = data.benchmark.scale_percentile
    if p is None or data.benchmark.mean_daily_per_trade_area is None:
        return None
    rank = f"상위 {100 - p}%" if p >= 50 else f"하위 {p}%"
    return Finding(
        text=(
            f"상권 1곳당 하루 유동인구는 {data.benchmark.mean_daily_per_trade_area:,.0f}명으로 "
            f"서울 상권 중 {rank} 규모다."
        ),
        path="/benchmark/scale_percentile",
    )


def _peak(
    index: dict[str, float | None], labels: dict[str, str], what: str, base: str
) -> Finding | None:
    """가장 높은 칸을 고른다. 두드러지지 않으면 "평균과 비슷하다" 고 쓴다."""
    if not index or any(value is None for value in index.values()):
        return None
    key = max(index, key=lambda key: index[key] or 0.0)
    value = index[key]
    assert value is not None
    if value >= HIGH:
        text = f"{labels[key]} {what}이 서울 평균의 {value:.2f}배로 가장 두드러진다."
    else:
        text = f"{what}은 서울 평균과 비슷하다(가장 높은 {labels[key]}도 {value:.2f}배)."
    return Finding(text=text, path=f"{base}/{key}")
