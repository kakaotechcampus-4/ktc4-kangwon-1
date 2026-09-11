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

import math

import httpx

from app.schemas import AgentAnalysis, AgentError, AnalysisTask, Scope

from . import baseline
from .classify import classify
from .client import MissingApiKeyError, SeoulOpenApiError, SeoulOpenDataClient
from .config import Settings, load_dotenv_if_present
from .geo import to_epsg5181
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
    Reliability,
    Source,
    TradeArea,
    TypeJudgement,
)

AGENT_ID = "floating_population"

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
    되므로 단위를 명시하고 일평균(`daily_avg`)도 함께 낸다.
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
        unit=f"명 ({period_ko(quarter)} 합계, 같은 사람의 반복 통행이 중복 집계됨)",
        share_unit="비율 (0~1)",
        total=float(total),
        daily_avg=round(total / days, 1),
        male=float(sum(r.male for r in records)),
        female=float(female),
        female_ratio=round(female / denom, 4),
        by_age={a: float(v) for a, v in by_age.items()},
        age_share={a: round(by_age[a] / denom, 4) for a in AGE_BANDS},
        by_time={b: float(v) for b, v in by_time.items()},
        time_per_hour_share={b: round(per_hour[b] / ph_sum, 4) for b in TIME_BANDS},
        peak_time_band=max(TIME_BANDS, key=per_hour.__getitem__),
        by_day={d: float(v) for d, v in by_day.items()},
        weekday_avg=round(weekday_avg, 1),
        weekend_avg=round(weekend_avg, 1),
        weekend_to_weekday_ratio=round(weekend_avg / weekday_avg, 4) if weekday_avg else 0.0,
    )


def _benchmark(population: Population, trade_area_count: int) -> Benchmark:
    """서울 평균 대비 상대지표. 결정 에이전트가 점수를 계산하는 근거다."""
    time_index = baseline.time_indices(population.time_per_hour_share)
    mean_per_area = population.total / (trade_area_count or 1)
    return Benchmark(
        unit="배수 (1.0 = 서울 전체 상권 평균)",
        baseline=baseline.BASELINE_LABEL,
        age_index={
            a: baseline.index(population.age_share[a], baseline.AGE_SHARE_AVG[a])
            for a in AGE_BANDS
        },
        time_per_hour_index=time_index,
        lunch_index=time_index["11_14"],
        evening_index=time_index["17_21"],
        night_index=time_index["21_24"],
        weekend_index=baseline.index(
            population.weekend_to_weekday_ratio, baseline.WEEKEND_TO_WEEKDAY_AVG
        ),
        mean_per_trade_area=round(mean_per_area, 1),
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
        "population 의 인원수는 분기 합계이며 같은 사람의 반복 통행이 중복 집계됩니다 — "
        "하루 평균이 필요하면 population.daily_avg 를 쓰십시오. "
        "benchmark 는 서울 전체 상권 평균 대비 배수(1.0 = 평균)입니다. "
        "업종별 점포수·매출·임대료는 이 자료에 없습니다."
    )


def _reliability(found: int, covered: int) -> Reliability:
    """상권 표본이 얼마나 두터운지. 결정 에이전트가 가중치를 낮추는 근거."""
    if covered <= 1:
        level = "low"
    elif covered < 3 or covered < found:
        level = "medium"
    else:
        level = "high"
    return Reliability(trade_area_count=found, covered_trade_areas=covered, level=level)


def analyze(
    task: AnalysisTask,
    *,
    settings: Settings | None = None,
    client: SeoulOpenDataClient | None = None,
) -> AgentAnalysis:
    """입력 위치 반경 안의 유동인구를 분석해 팀 공통 계약 형태로 돌려준다."""
    site = task.site
    if settings is None:
        load_dotenv_if_present()
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

    try:
        client = client or SeoulOpenDataClient(settings)
    except MissingApiKeyError as e:
        return failed("CONFIG_ERROR", str(e))

    x, y = to_epsg5181(site.latitude, site.longitude)

    try:
        areas = client.fetch_trdar_areas()
        hits = _overlapping_areas(areas, x, y, radius)
        if not hits:
            return empty(
                "해당 없음",
                f"{site.input_address} 기준 반경 {radius}m 와 겹치는 "
                "서울시 상권분석서비스 상권이 없습니다",
            )
        quarter, records = client.fetch_flpop({a.trdar_cd for a, _ in hits})
    except httpx.TimeoutException as e:
        return failed("UPSTREAM_TIMEOUT", f"서울시 API 응답 시간이 초과되었습니다: {e}")
    except (SeoulOpenApiError, httpx.HTTPError) as e:
        return failed("UPSTREAM_ERROR", f"서울시 API 오류: {e}")

    if not records:
        return empty(
            period_ko(quarter),
            f"겹치는 상권 {len(hits)}곳의 {period_ko(quarter)} 유동인구 자료가 없습니다",
        )

    population = _aggregate(records, quarter)
    covered = len(records)
    type_result = classify(
        age_share=population.age_share,
        weekend_to_weekday=population.weekend_to_weekday_ratio,
    )
    reliability = _reliability(len(hits), covered)

    warnings = list(BASE_WARNINGS)
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
            f"반경 {radius}m 와 겹치는 상권이 1곳뿐이라(총 {population.total:,.0f}명) "
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
        benchmark=_benchmark(population, covered),
        type=TypeJudgement(signals_unit="비율 (0~1). 주말/주중은 배수", **type_result.model_dump()),
        reliability=reliability,
        sources=[Source(**s, period=period_ko(quarter)) for s in SOURCES],
    )

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
