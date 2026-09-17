"""유동인구 분석 에이전트.

    AnalysisTask ─▶ 위경도→EPSG:5181 ─▶ 반경과 겹치는 상권 선택 ─▶ 길단위인구 조회
                       (geo.py)           (상권영역 API)       (길단위인구 API)
    ─▶ 합산·분포 ─▶ 유형 판정 ─▶ 서울 평균 대비 지표 ─▶ AgentAnalysis
                   (classify.py)        (baseline.py)

프레임워크를 쓰지 않는다. 분기 없는 직선 흐름이라 함수 호출로 충분하다(테크 스펙의
"에이전트 프레임워크 없이 직접 구현"과 같은 방향).

**예외를 던지지 않는다.** 오케스트레이터가 세 분석 에이전트를 병렬로 돌리므로 하나가 예외를
던지면 전체가 죽는다. 모든 실패를 계약 status 로 바꿔서 돌려준다.
"""

from __future__ import annotations

import json
import math
from collections.abc import Awaitable, Callable
from typing import Literal

import httpx

from app.schemas import AgentAnalysis, AgentError, AgentId, AnalysisTask, Scope

from . import baseline, llm
from .classify import classify
from .client import MissingApiKeyError, SeoulOpenApiError, SeoulOpenDataClient
from .config import Settings
from .geo import circle_overlap_ratio, to_epsg5181
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
    FloatingPopulationData,
    Population,
    QuarterPoint,
    RadiusPoint,
    RadiusProfile,
    Reliability,
    Selection,
    Source,
    TradeArea,
    Trend,
    TypeJudgement,
)

AGENT_ID: AgentId = "floating_population"

# 선별 함수 자리. 테스트에서 갈아 끼운다(팀 `decision.analyze(generate=...)` 와 같은 방식).
SelectBlocks = Callable[[str], Awaitable[tuple[list[str], str]]]

SOURCES = [
    {
        "name": "서울시 상권분석서비스(길단위인구-상권)",
        "url": "https://data.seoul.go.kr/dataList/OA-15568/S/1/datasetView.do",
        "license": "공공누리 1유형(출처표시)",
    },
    {
        "name": "서울시 상권분석서비스(영역-상권)",
        "url": "https://data.seoul.go.kr/dataList/OA-15560/S/1/datasetView.do",
        "license": "공공누리 1유형(출처표시)",
    },
]

# 상권 구역(면적 등가원)을 반경 판정에 반영할 상한 — 반경의 절반까지만 인정한다.
# 근거는 `_overlapping_areas` 의 표에 있다. 바꾸면 집계에 들어오는 상권이 달라진다.
_MAX_AREA_REACH_RATIO = 0.5

BASE_WARNINGS = [
    "유동인구 유형은 직업 데이터가 아닌 연령·요일 분포에서 추정한 값입니다.",
    "상권영역 API 가 폴리곤을 주지 않아 상권 구역을 면적 등가원으로 근사했습니다.",
]


def _overlapping_areas(
    areas: list[TrdarArea], x: float, y: float, radius_m: float
) -> list[tuple[TrdarArea, float]]:
    """반경과 구역이 겹치는 상권을 (상권, 대표점까지의 거리) 로 가까운 순 반환.

    상권영역 API 가 폴리곤을 주지 않아 구역을 **면적 등가원**으로 근사하고, 대표 점까지의
    거리에서 등가 반지름을 빼서 반경과 비교한다. **단 등가 반지름은 반경의 절반까지만
    인정한다**(`_MAX_AREA_REACH_RATIO`).

    상한이 왜 필요한지는 실데이터로 확인했다(2026Q2, 반경 500m 기준):

    | 기준 | 서교동 분석 | 역삼1동 최대 단일 기여 | 도달 거리 |
    | --- | --- | --- | --- |
    | 대표 점 거리만 | `서교동(홍대)` 상권 누락 | 역삼역 68.1% | 611m |
    | 등가 반지름 전부 인정 | 포함 | **강남역 37.6%** | 1,287m |
    | 등가 반지름 상한 절반 | 포함 | 역삼역 37.8% | 870m |

    - 상한이 없으면 등가 반지름이 400m 대인 발달상권이 판정 반경을 두 배로 늘린다. 실제로
      843m 떨어진 `강남역` 상권이 테헤란로 분석에 들어와 전체의 37.6% 를 차지했다.
    - 반대로 대표 점 거리만 보면 큰 상권이 통째로 빠진다(등가 반지름 중위 151m, 상위 10% 는
      255m 이상). 서교동(홍대) 분석에서 `서교동(홍대)` 상권 자체가 빠지는 결과가 나왔다.
    - 상한을 반경의 1/3 로 더 조이면 그 누락이 다시 생긴다. 절반이 두 결함을 모두 피하는
      지점이다.

    집계 범위는 여전히 반경보다 넓다(반경에 걸친 상권은 구역 전체가 들어온다). 그래서 scope
    와 warnings 에 실제 도달 거리를 적는다. 좌표계가 EPSG:5181(미터) 이라 유클리드 거리를
    그대로 쓴다.
    """
    max_reach = radius_m * _MAX_AREA_REACH_RATIO
    hits = []
    for area in areas:
        distance = math.hypot(area.x - x, area.y - y)
        if distance - min(area.equivalent_radius_m, max_reach) <= radius_m:
            hits.append((area, distance))
    return sorted(hits, key=lambda h: h[1])


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


def _description(quarter: str, covered: int, outer_reach: float, radius_m: int) -> str:
    """`data` 맨 앞에 붙는 설명.

    결정 에이전트 프롬프트가 "필드 이름, 설명, 단위와 실제 값을 함께 읽는다" 고 했고, 목업의
    다른 두 에이전트도 `description` 을 넣는다. 특히 **인원수가 분기 합계라는 점**을 글로
    밝혀야 한다 — 목업 유동인구가 `daily_average` 15,200명/일 이라, 단위를 안 적으면 분기
    합계를 일평균으로 읽어 1,000배 오독한다.
    """
    return (
        f"서울시 상권분석서비스 길단위인구(통신사 기반) 자료입니다. "
        f"입력 좌표 반경 {radius_m}m 와 겹치는 상권 {covered}곳의 {period_ko(quarter)} 값을 "
        f"합산했습니다(구역이 반경에 걸친 상권은 전체를 포함해 실제 바깥 경계는 약 "
        f"{outer_reach:,.0f}m 입니다). "
        "여기서 '상권' 은 서울시가 정의한 분석 구역(골목상권·발달상권·전통시장·관광특구)이고 "
        "지하철 출구·시장·아파트 단위로 잘려 있어 서로 경쟁하는 별개 상권이 아닙니다 — "
        f"상권 {covered}곳은 같은 지역을 나눈 조각 {covered}개라는 뜻이며 인접 동네 {covered}개가 "
        "아닙니다. "
        "인원수는 population.daily_avg(명/일) 하나로만 냅니다 — 분기 합계는 다른 에이전트의 "
        "'명/일' 과 나란히 놓였을 때 오독되므로 싣지 않습니다. 같은 사람의 반복 통행이 "
        "중복 집계된 통행량이며 사람 수가 아닙니다. "
        "분기 합계 원값은 population 의 by_age·by_time·by_day 에만 남아 있습니다. "
        "benchmark 는 서울 전체 상권 평균 대비 배수(1.0 = 평균)입니다. "
        "trend 는 같은 상권들을 분기마다 다시 합산한 추세로 quarters 가 오래된 순이며, "
        "변화율(qoq_change·yoy_change)은 분기 일수 차이를 없앤 daily_avg 기준입니다. "
        "radius_profile 은 반경별 인구인데 원자료가 상권 조각 단위라 반경으로 정확히 자를 수 "
        "없어 겹친 면적 비율로 안분한 추정값입니다 — 실측값이 아닙니다. "
        "시간대는 원자료가 6구간(00-06·06-11·11-14·14-17·17-21·21-24)뿐이라 더 잘게 나눌 수 "
        "없고, 구간 길이가 3~6시간으로 달라 비교는 반드시 time_per_hour_share 로 해야 합니다 "
        "— by_time 총량으로 비교하면 6시간짜리 00-06 구간이 거의 항상 1위가 됩니다. "
        "업종별 점포수·매출·임대료는 이 자료에 없습니다."
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


def _selection_digest(data: FloatingPopulationData) -> str:
    """선별 모델에게 보낼 요약. **`data` 전체를 보내지 않는다.**

    전체를 보내면 줄이려던 토큰을 선별하느라 그대로 쓰게 된다. 블록마다 "읽을 게 있는지" 를
    판단할 최소 정보만 추린다 — 개수, 값의 폭, 0 이 몇 개인지 같은 것들.
    """
    rp = data.radius_profile
    tr = data.trend
    digest = {
        "지역": data.description[:120],
        "유형": data.type.label,
        "신뢰도": data.reliability.level,
        "trade_areas": {
            "개수": len(data.trade_areas or []),
            "이름": [t.name for t in (data.trade_areas or [])][:12],
            "행정동": sorted({t.adstrd for t in (data.trade_areas or []) if t.adstrd}),
        },
        "population_raw": {
            "설명": "연령·시간대·요일 원값(분기 합계). 같은 내용의 비중이 따로 있음",
            "비중_이미_있음": True,
        },
        "radius_profile": {
            "단계": [p.radius_m for p in (rp.points if rp else [])],
            "일평균": [round(p.daily_avg) for p in (rp.points if rp else [])],
            "값이_0인_단계수": sum(1 for p in (rp.points if rp else []) if p.daily_avg <= 0),
        },
        "trend": {
            "분기수": len(tr.quarters) if tr else 0,
            "방향": tr.direction if tr else None,
            "전분기_변화율": tr.qoq_change if tr else None,
            "전년동기_변화율": tr.yoy_change if tr else None,
            "일평균_추이": [round(q.daily_avg) for q in (tr.quarters if tr else [])],
        },
    }
    return json.dumps(digest, ensure_ascii=False)


async def _select(
    data: FloatingPopulationData,
    select: SelectBlocks | None,
) -> tuple[Selection, str | None]:
    """블록을 고른다. 실패하면 전부 싣고 그 사실을 경고로 돌려준다."""
    selectable = list(llm.SELECTABLE)
    try:
        included, reason = await (select or llm.select_blocks)(_selection_digest(data))
    except llm.SelectionUnavailable:
        return (
            Selection(
                applied=False,
                selectable=selectable,
                included=selectable,
                dropped=[],
                unavailable_reason="자료 선별 기능을 사용할 수 없습니다.",
            ),
            None,  # 키가 없어 못 한 경우까지 경고로 띄우면 시끄럽다
        )
    except Exception:  # 모델 쪽 어떤 실패도 분석을 막지 않는다
        return (
            Selection(
                applied=False,
                selectable=selectable,
                included=selectable,
                dropped=[],
                unavailable_reason="자료 선별 중 오류가 발생했습니다.",
            ),
            "자료 선별에 실패해 전부 실었습니다.",
        )

    dropped = [b for b in selectable if b not in included]
    return (
        Selection(
            applied=True,
            selectable=selectable,
            included=included,
            dropped=dropped,
            reason=(reason or None) if dropped else None,
        ),
        None,
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


async def analyze(
    task: AnalysisTask,
    *,
    settings: Settings | None = None,
    client: SeoulOpenDataClient | None = None,
    select: SelectBlocks | None = None,
) -> AgentAnalysis:
    """입력 위치 반경 안의 유동인구를 분석해 팀 공통 계약 형태로 돌려준다.

    오케스트레이터가 분석 에이전트를 `asyncio.gather` 로 동시에 돌리므로 비동기다
    (`orchestrator.AnalysisAgent = Callable[[AnalysisTask], Awaitable[AgentAnalysis]]`).
    클라이언트를 주입하지 않으면 여기서 만들고 끝날 때 닫는다.
    """
    site = task.site
    if settings is None:
        settings = Settings.from_env()
    radius = settings.analysis_radius_m
    # ⚠️ 이 문자열은 `commercial_area` 와 **글자까지 같아야 한다.** 결정 에이전트가
    # `{(scope.area, scope.period)}` 집합의 크기로 불일치를 판정하고(agent.py 의 `scopes`),
    # 하나라도 다르면 "분석 지역 또는 기준 기간이 달라 비교하기 어렵다" 를 한계로 붙인다.
    # 같은 지역인데 표기만 달라서 그 한계가 붙는 일이 없도록 `commercial_area/agent.py` 의
    # `scope_area = f"{site.input_address} 반경 {radius}m"` 와 형식을 맞춘다.
    # (행정동은 `trade_areas[].adstrd`, 실제 도달 거리는 warnings 에 있다)
    area_label = f"{site.input_address} 반경 {radius}m"

    def failed(code: str, message: str) -> AgentAnalysis:
        return AgentAnalysis(
            request_id=task.request_id,
            agent_id=AGENT_ID,
            status="error",
            scope=None,
            data={},
            error=AgentError(code=code, message=message),
            warnings=[message],
        )

    def empty(period: str, message: str) -> AgentAnalysis:
        return AgentAnalysis(
            request_id=task.request_id,
            agent_id=AGENT_ID,
            status="no_data",
            scope=Scope(area=area_label, period=period),
            data={},
            error=None,
            warnings=[message],
        )

    owns_client = client is None
    try:
        client = client or SeoulOpenDataClient(settings)
    except MissingApiKeyError:
        return failed("CONFIG_ERROR", "유동인구 API 설정을 확인해 주세요.")

    x, y = to_epsg5181(site.latitude, site.longitude)

    # 네트워크를 쓰는 구간은 여기뿐이다. 아래 계산은 전부 로컬이라 끝나는 대로 연결을 닫는다.
    try:
        areas = await client.fetch_trdar_areas()
        hits = _overlapping_areas(areas, x, y, radius)
        if not hits:
            return empty(
                "해당 없음",
                f"{site.input_address} 기준 반경 {radius}m 와 겹치는 "
                "서울시 상권분석서비스 상권이 없습니다",
            )
        # 반경별 곡선은 분석 반경보다 넓게 본다. 상권 선택은 로컬 계산이고 길단위인구는 어차피
        # 분기 전체를 받아 거르므로, 넓혀도 **API 호출은 늘지 않는다.**
        scan_radius = max(radius, max(settings.radius_profile_m, default=radius))
        scan_hits = _overlapping_areas(areas, x, y, scan_radius)
        main_codes = {a.trdar_cd for a, _ in hits}
        wanted = main_codes | {a.trdar_cd for a, _ in scan_hits}
        series = await client.fetch_flpop_series(wanted, settings.trend_quarters)
        quarter, latest = series[-1]
        records = [r for r in latest if r.trdar_cd in main_codes]
    except httpx.TimeoutException:
        return failed("UPSTREAM_TIMEOUT", "서울시 API 응답 시간이 초과되었습니다.")
    except (SeoulOpenApiError, httpx.HTTPError):
        return failed("UPSTREAM_ERROR", "서울시 API 조회에 실패했습니다.")
    finally:
        if owns_client:
            await client.aclose()

    if not records:
        return empty(
            period_ko(quarter),
            f"겹치는 상권 {len(hits)}곳의 {period_ko(quarter)} 유동인구 자료가 없습니다",
        )

    population = _aggregate(records, quarter)
    # 분기 합계는 내보내지 않지만 규모 백분위를 낼 때는 필요하다(서울 기준선이 분기 합계
    # 기준으로 측정돼 있다). 계산에만 쓰고 `data` 에는 싣지 않는다.
    quarter_total = sum(r.total for r in records)
    covered = len(records)
    type_result = classify(
        age_share=population.age_share,
        weekend_to_weekday=population.weekend_to_weekday_ratio,
    )
    reliability = _reliability(len(hits), covered)
    trend = _trend(series, main_codes)

    warnings = list(BASE_WARNINGS)
    warnings.append(
        "radius_profile 은 상권 안 인구가 고르게 분포한다고 보고 면적 비율로 안분한 "
        "추정값입니다 — 원자료가 상권 조각 단위라 반경으로 정확히 자를 수 없습니다."
    )
    if len(trend.quarters) < settings.trend_quarters:
        warnings.append(
            f"추세는 {settings.trend_quarters}개 분기를 요청해 "
            f"{len(trend.quarters)}개 분기만 자료가 있었습니다."
        )
    # 분기마다 집계된 상권 수가 다르면 증감이 표본 변화일 수 있다.
    counts = {p.trade_area_count for p in trend.quarters}
    if len(counts) > 1:
        warnings.append(
            f"분기마다 자료가 있는 상권 수가 달라({min(counts)}~{max(counts)}곳) "
            "추세의 증감에 표본 변화가 섞여 있을 수 있습니다."
        )
    # 반경에 걸친 상권은 구역 전체가 집계에 들어간다. 실제로 어디까지 미치는지 밝혀 둔다.
    outer_reach = max(d + a.equivalent_radius_m for a, d in hits)
    if outer_reach > radius:
        warnings.append(
            f"반경에 걸친 상권은 구역 전체를 집계했습니다 — 가장 바깥 경계는 약 "
            f"{outer_reach:,.0f}m 로 반경 {radius}m 를 넘습니다."
        )
    if covered < len(hits):
        warnings.append(
            f"겹치는 상권 {len(hits)}곳 중 {covered}곳만 자료가 있어 그만큼만 집계했습니다."
        )
    # 상권이 하나면 분포가 그 상권 하나에 전적으로 좌우된다 — 결정 에이전트가 무게를 낮춰야 한다.
    if covered == 1:
        warnings.append(
            f"반경 {radius}m 와 겹치는 상권이 1곳뿐이라(일평균 {population.daily_avg:,.0f}명) "
            "분포가 그 상권 하나에 좌우됩니다. 판정 신뢰도를 낮게 보십시오."
        )

    data = FloatingPopulationData(
        description=_description(quarter, covered, outer_reach, radius),
        period_code=quarter,
        radius_m=radius,
        trade_areas=[
            TradeArea(
                code=a.trdar_cd,
                name=a.trdar_cd_nm,
                kind=a.trdar_se_nm,
                adstrd=a.adstrd_nm,
                distance_m=round(d, 1),
                area_m2=round(a.relm_ar, 1),
                equivalent_radius_m=round(a.equivalent_radius_m, 1),
            )
            for a, d in hits
        ],
        population=population,
        benchmark=_benchmark(population, quarter_total, covered, quarter_days(quarter)),
        trend=trend,
        radius_profile=_radius_profile(
            scan_hits,
            {r.trdar_cd: r for r in latest},
            settings.radius_profile_m,
            quarter_days(quarter),
        ),
        type=TypeJudgement(signals_unit="비율 (0~1). 주말/주중은 배수", **type_result.model_dump()),
        reliability=reliability,
        # 바로 아래에서 실제 선별 결과로 덮어쓴다. 모델이 없거나 실패해도 계약은 채워진다.
        selection=Selection(
            applied=False,
            selectable=list(llm.SELECTABLE),
            included=list(llm.SELECTABLE),
            dropped=[],
        ),
        sources=[Source(**s, period=period_ko(quarter)) for s in SOURCES],
    )

    # 넘길 블록을 고른다. 숫자는 이미 다 계산돼 있고 모델은 고르기만 한다.
    selection, select_warning = await _select(data, select)
    data.selection = selection
    # 원본 차트는 반환·저장하고 최종판단이 프롬프트 복사본에만 선별을 적용합니다.
    if selection.applied and selection.dropped:
        warnings.append(
            f"최종판단 입력에서만 자료 {len(selection.dropped)}개를 제외합니다"
            f"({', '.join(selection.dropped)}). {selection.reason}".strip()
        )
    if select_warning:
        warnings.append(select_warning)

    return AgentAnalysis(
        request_id=task.request_id,
        agent_id=AGENT_ID,
        # 자료가 있는 상권이 반경 안 상권보다 적으면 "일부만 확보" 다.
        status="ok" if covered == len(hits) else "partial",
        scope=Scope(area=area_label, period=period_ko(quarter)),
        data=data.model_dump(mode="json"),
        error=None,
        warnings=warnings,
    )
