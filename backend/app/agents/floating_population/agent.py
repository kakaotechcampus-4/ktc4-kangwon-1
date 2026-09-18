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

import httpx

from app.schemas import AgentAnalysis, AgentError, AgentId, AnalysisTask, Scope

from . import llm
from .classify import classify
from .client import MissingApiKeyError, SeoulOpenApiError, SeoulOpenDataClient
from .config import Settings
from .geo import _overlapping_areas, to_epsg5181
from .llm import SelectBlocks
from .metrics import _aggregate, _benchmark, _radius_profile, _reliability, _trend
from .models import period_ko, quarter_days
from .schemas import (
    FloatingPopulationData,
    Selection,
    Source,
    TradeArea,
    TypeJudgement,
)

AGENT_ID: AgentId = "floating_population"

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

BASE_WARNINGS = [
    "유동인구 유형은 직업 데이터가 아닌 연령·요일 분포에서 추정한 값입니다.",
    "상권영역 API 가 폴리곤을 주지 않아 상권 구역을 면적 등가원으로 근사했습니다.",
]


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
    selection, select_warning = await llm._select(data, select)
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
