"""유동인구 지표 계산."""

from typing import Literal

from . import baseline
from .geo import circle_overlap_ratio
from .models import (
    AGE_BANDS,
    DAYS,
    TIME_BAND_HOURS,
    TIME_BANDS,
    WEEKDAYS,
    WEEKEND,
    FlpopRecord,
    TrdarArea,
    period_ko,
    quarter_days,
)
from .schemas import (
    Benchmark,
    Population,
    QuarterPoint,
    RadiusPoint,
    RadiusProfile,
    Reliability,
    Trend,
)


def _aggregate(records: list[FlpopRecord], quarter: str) -> Population:
    """여러 상권의 같은 분기 레코드를 하나로 합산하고 비중까지 계산한다.

    원본 인원수는 **분기 합계**다. 결정 에이전트가 다른 에이전트의 "명/일" 과 나란히 읽게
    되므로 **일평균(`daily_avg`)으로만** 내보내고 합계는 싣지 않는다. 합계 원값이 남는 곳은
    `by_age`·`by_time`·`by_day` 뿐이다.
    """
    total = sum(r.total for r in records)
    denom = total or 1.0
    female = sum(r.female for r in records)

    by_age = {a: sum(r.by_age[a] for r in records) for a in AGE_BANDS}
    by_time = {b: sum(r.by_time[b] for r in records) for b in TIME_BANDS}
    by_day = {d: sum(r.by_day[d] for r in records) for d in DAYS}

    # 시간대는 반드시 시간당 값으로 비교한다. 구간 길이가 3~6시간으로 달라서 총량으로 비교하면
    # 6시간짜리 00~06시가 거의 항상 1위가 된다(실데이터에서 확인된 왜곡).
    per_hour = {b: by_time[b] / TIME_BAND_HOURS[b] for b in TIME_BANDS}
    ph_sum = sum(per_hour.values()) or 1.0

    weekday_avg = sum(by_day[d] for d in WEEKDAYS) / len(WEEKDAYS)
    weekend_avg = sum(by_day[d] for d in WEEKEND) / len(WEEKEND)

    days = quarter_days(quarter)
    return Population(
        unit=(
            f"daily_avg 는 명/일 ({period_ko(quarter)} 합계 ÷ {days}일). "
            "같은 사람의 반복 통행이 중복 집계된 통행량이며 사람 수가 아님. "
            "by_age·by_time·by_day 는 분기 합계 원값"
        ),
        share_unit="비율 (0~1)",
        daily_avg=round(total / days, 1),
        female_ratio=round(female / denom, 4),
        by_age={a: float(v) for a, v in by_age.items()},
        age_share={a: round(by_age[a] / denom, 4) for a in AGE_BANDS},
        by_time={b: float(v) for b, v in by_time.items()},
        time_per_hour_share={b: round(per_hour[b] / ph_sum, 4) for b in TIME_BANDS},
        peak_time_band=max(TIME_BANDS, key=per_hour.__getitem__),
        by_day={d: float(v) for d, v in by_day.items()},
        weekend_to_weekday_ratio=round(weekend_avg / weekday_avg, 4) if weekday_avg else 0.0,
    )


def _benchmark(
    population: Population, quarter_total: float, trade_area_count: int, days: int
) -> Benchmark:
    """서울 평균 대비 상대지표. 결정 에이전트가 점수를 계산하는 근거다.

    `scale_percentile` 은 서울 기준선이 분기 합계로 측정돼 있어 분기 합계로 계산하지만,
    밖으로 내보낼 때는 일평균으로 바꾼다 — 이 블록의 `unit` 이 "배수" 라 분기 합계가 섞이면
    표기가 어긋나고, 다른 에이전트의 "명/일" 옆에서 오독된다.
    """
    time_index = baseline.time_indices(population.time_per_hour_share)
    mean_per_area = quarter_total / (trade_area_count or 1)
    return Benchmark(
        unit="배수 (1.0 = 서울 전체 상권 평균). 단 mean_daily_per_trade_area 는 명/일",
        baseline=baseline.BASELINE_LABEL,
        age_index={
            a: baseline.index(population.age_share[a], baseline.AGE_SHARE_AVG[a]) for a in AGE_BANDS
        },
        time_per_hour_index=time_index,
        lunch_index=time_index["11_14"],
        evening_index=time_index["17_21"],
        night_index=time_index["21_24"],
        weekend_index=baseline.index(
            population.weekend_to_weekday_ratio, baseline.WEEKEND_TO_WEEKDAY_AVG
        ),
        mean_daily_per_trade_area=round(mean_per_area / days, 1),
        scale_percentile=baseline.scale_percentile(mean_per_area),
    )


def _trend(series: list[tuple[str, list[FlpopRecord]]], main_codes: set[str]) -> Trend:
    """분기별 추세. 최신 1개 분기만 보던 단면 분석의 한계를 푼다.

    **같은 상권 집합으로 분기마다 다시 합산한다.** 반경 판정은 상권영역(시점 없는 현재
    스냅샷)으로 한 번만 하므로 분기가 바뀌어도 대상 상권은 같다. 다만 그 분기에 자료가 없는
    상권이 있을 수 있어(서울 전체가 1,648~1,650곳 사이에서 오르내린다) 분기마다 실제 집계된
    상권 수를 함께 싣는다 — 증감이 상권 수 변화 때문일 수 있기 때문이다.

    변화율은 `daily_avg` 로 잰다. 분기 합계는 분기 일수(90~92일)가 달라 그대로 비교하면
    최대 2% 의 가짜 증감이 섞인다.
    """
    points_by_quarter: dict[str, QuarterPoint] = {}
    requested_quarters = {quarter for quarter, _ in series}
    latest_quarter = max(requested_quarters, default=None)
    for quarter, records in series:
        rs = [r for r in records if r.trdar_cd in main_codes]
        if not rs:
            continue  # 그 분기 자료가 없는 구간. 점을 만들지 않아 그래프에 구멍으로 남는다.
        pop = _aggregate(rs, quarter)
        points_by_quarter[quarter] = QuarterPoint(
            period_code=quarter,
            period=period_ko(quarter),
            daily_avg=round(pop.daily_avg, 1),
            trade_area_count=len(rs),
            age_share=pop.age_share,
            time_per_hour_share=pop.time_per_hour_share,
        )

    points = [points_by_quarter[quarter] for quarter in sorted(points_by_quarter)]

    def change(new: float, old: float) -> float | None:
        return round((new - old) / old, 4) if old else None

    def previous_quarter(quarter: str, count: int = 1) -> str:
        year, number = int(quarter[:4]), int(quarter[4])
        index = year * 4 + number - 1 - count
        return f"{index // 4}{index % 4 + 1}"

    latest = points_by_quarter.get(latest_quarter or "")
    previous = points_by_quarter.get(previous_quarter(latest_quarter)) if latest_quarter else None
    previous_year = (
        points_by_quarter.get(previous_quarter(latest_quarter, 4)) if latest_quarter else None
    )
    qoq = change(latest.daily_avg, previous.daily_avg) if latest and previous else None
    yoy = change(latest.daily_avg, previous_year.daily_avg) if latest and previous_year else None

    # 전년 동기가 있으면 그걸로 본다 — 계절성이 빠져서 판단에 낫다.
    basis = yoy if yoy is not None else qoq
    if basis is None:
        direction = "판단 불가"
    elif basis > 0.05:
        direction = "증가"
    elif basis < -0.05:
        direction = "감소"
    else:
        direction = "보합"

    return Trend(
        unit="명 (분기 합계) · daily_avg 는 명/일 · 변화율은 비율(0.05 = +5%)",
        quarters=points,
        qoq_change=qoq,
        yoy_change=yoy,
        direction=direction,
    )


def _radius_profile(
    scan_hits: list[tuple[TrdarArea, float]],
    by_cd: dict[str, FlpopRecord],
    radii: tuple[int, ...],
    days: int,
) -> RadiusProfile:
    """반경을 넓혀가며 본 인구 곡선. **면적 안분**으로 낸다.

    원자료가 상권 조각 단위라 정직한 반경 절단이 안 된다. 대표 점이 반경 안이면 상권을
    통째로 세는 방식은 반경을 줄일수록 무너진다 — 실측(2026Q2)으로 확인한 것:

    | 반경 | 길동 | 테헤란로 | 서교동 | 평창동 |
    | --- | --- | --- | --- | --- |
    | 100m | 0곳 | 1곳(100%) | 0곳 | 0곳 |
    | 250m | 4곳 | 1곳(100%) | 1곳(100%) | 0곳 |
    | 500m | 9곳 | 8곳 | 12곳 | 2곳 |

    테헤란로 100m 의 "상권 1곳" 은 실제 도달 거리가 483m 이고, 서교동은 250m→500m 에서
    합계가 **+2,981%** 튄다. 조각이 하나 들어오고 나가는 데 따라 계단식으로 뛰기 때문이다.

    그래서 반경 원과 상권 면적 등가원의 **겹친 면적 비율**만큼만 인구를 센다. 반경이 줄면
    값도 부드럽게 줄고 100m 에서도 0 이 되지 않는다. 대신 **상권 안에서 인구가 고르게
    분포한다**는 가정이 들어가므로 `method` 에 그대로 적어 결정·리포트 쪽이 알게 한다.
    """
    points: list[RadiusPoint] = []
    for r in sorted(radii):
        total = 0.0
        weight_sum = 0.0
        touched = 0
        for area, distance in scan_hits:
            record = by_cd.get(area.trdar_cd)
            if record is None:
                continue
            w = circle_overlap_ratio(distance, r, area.equivalent_radius_m)
            if w <= 0:
                continue
            total += record.total * w
            weight_sum += w
            touched += 1
        points.append(
            RadiusPoint(
                radius_m=r,
                total=round(total, 1),
                daily_avg=round(total / days, 1),
                trade_area_count=touched,
                effective_trade_areas=round(weight_sum, 2),
            )
        )
    return RadiusProfile(
        unit="명 (분기 합계) · daily_avg 는 명/일",
        method=(
            "면적 안분 — 상권 구역을 면적 등가원으로 근사하고, 반경 원과 겹친 면적 비율만큼 "
            "인구를 나눠 셌습니다. 상권 안에서 인구가 고르게 분포한다고 가정한 값이므로 "
            "실측값이 아니라 추정값입니다. 원자료가 상권 조각 단위라 반경으로 정확히 자를 수 "
            "없어 쓰는 방법입니다. "
            "⚠️ 그래서 같은 반경이라도 population 의 값보다 작습니다 — population 은 반경에 "
            "걸친 상권을 구역째 합산하고(바깥 경계가 반경을 넘습니다), 이 곡선은 겹친 만큼만 "
            "셉니다. 서로 다른 질문의 답이지 모순이 아닙니다. 지역의 대표 수치로는 "
            "population 을, 반경에 따른 증가 추이로는 이 곡선을 쓰십시오."
        ),
        points=points,
    )


def _reliability(found: int, covered: int) -> Reliability:
    """상권 표본이 얼마나 두터운지. 결정 에이전트가 가중치를 낮추는 근거."""
    level: Literal["high", "medium", "low"]
    if covered <= 1:
        level = "low"
    elif covered < 3 or covered < found:
        level = "medium"
    else:
        level = "high"
    return Reliability(trade_area_count=found, covered_trade_areas=covered, level=level)
