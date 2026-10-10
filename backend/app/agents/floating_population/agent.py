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

import asyncio
import csv
from collections.abc import Callable

import httpx

from app.geo import to_epsg5181
from app.schemas import AgentAnalysis, AgentError, AgentId, AnalysisTask, Scope
from app.seoul import SeoulOpenApiTimeout

from . import selection as selection_rules
from .classify import classify
from .client import MissingApiKeyError, SeoulOpenApiError, SeoulOpenDataClient
from .config import Settings
from .geo import _overlapping_areas
from .interpret import interpret
from .metrics import _aggregate, _benchmark, _radius_profile, _reliability, _trend
from .models import PopulationRecord, missing_fields, period_ko, quarter_days
from .numeric import complete_sum
from .population import (
    RESIDENT_KIND,
    WORKER_KIND,
    load_snapshot,
    resident_block,
    summary_block,
    worker_block,
)
from .schemas import (
    FloatingPopulationData,
    ResidentPopulation,
    Selection,
    Source,
    TradeArea,
    TypeJudgement,
    WorkerPopulation,
)
from .selection import SelectBlocks

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
RESIDENT_SOURCE = {
    "name": "서울시 상권분석서비스(상주인구-상권)",
    "url": "https://data.seoul.go.kr/dataList/OA-15584/S/1/datasetView.do",
    "license": "공공누리 1유형(출처표시)",
}
WORKER_SOURCE = {
    "name": "서울시 상권분석서비스(직장인구-상권)",
    "url": "https://data.seoul.go.kr/dataList/OA-15569/S/1/datasetView.do",
    "license": "공공누리 1유형(출처표시)",
}

BASE_WARNINGS = [
    "유동인구 유형은 직업 데이터가 아닌 연령·요일 분포에서 추정한 값입니다.",
    "상권영역 API 가 폴리곤을 주지 않아 상권 구역을 면적 등가원으로 근사했습니다.",
]


def _description(quarter: str, covered: int, outer_reach: float, radius_m: int) -> str:
    """`data` 맨 앞에 붙는 설명 — **이번 요청에만 해당하는 사실**만 적는다.

    결정 에이전트 프롬프트가 "필드 이름, 설명, 단위와 실제 값을 함께 읽는다" 고 해서 두는
    자리다. 요청마다 같은 해석 규칙(daily_avg 는 통행량, 시간대는 시간당 값으로 비교,
    radius_profile 은 면적 안분 추정 등)은 결정 프롬프트 「유동인구 해석」 절에 이미 있어
    여기서 되풀이하지 않는다. 프롬프트에 아직 없는 것(상권 조각의 뜻, 인구 블록끼리 더하지
    않기)만 남긴다. 단위는 각 블록의 `unit` 에 있다.
    """
    return (
        f"서울시 상권분석서비스 자료입니다. 반경 {radius_m}m 와 겹치는 상권 {covered}곳의 "
        f"{period_ko(quarter)} 값을 합산했고, 반경에 걸친 상권은 구역 전체를 넣어 실제 바깥 "
        f"경계는 약 {outer_reach:,.0f}m 입니다. 상권은 서울시가 그은 분석 구역 조각이라 "
        f"{covered}곳이 동네 {covered}개라는 뜻이 아닙니다. "
        "population·trend·radius_profile 은 통행량(명/일, 중복 집계), resident·worker 는 "
        "사람 수(명)라 서로 더하지 않습니다. interpretation 은 코드가 이 자료의 숫자로 만든 "
        "요약 문장이며 path 가 근거 값입니다. 업종별 점포수·매출·임대료는 이 자료에 없습니다."
    )


def _load(kind: str) -> list[PopulationRecord] | None:
    """주거·직장인구 스냅샷 파일을 읽는다. **어떤 실패도 유동인구 분석을 막지 않는다.**

    세 분석 에이전트가 병렬로 돌아 예외 하나가 전체를 죽이므로, 파일이 없거나 깨져도 기존
    유동인구 결과는 그대로 나가야 한다. 실패는 블록을 비우고 warnings 로만 알린다.

    잡는 것은 **파일·형식 오류뿐**이다(없음·권한 = OSError, 값·검증 = ValueError, 컬럼 = KeyError,
    CSV 구조 = csv.Error). 그 밖의 예외는 코드 버그이므로 숨기지 않는다 — 오케스트레이터가 에이전트
    실패로 기록한다. 행이 하나도 없는 파일도 읽기 실패로 본다.
    """
    try:
        return load_snapshot(kind) or None
    except (OSError, ValueError, KeyError, csv.Error):
        return None


def _population_block[B: (ResidentPopulation, WorkerPopulation)](
    label: str,
    rows: list[PopulationRecord] | None,
    quarter: str,
    main_codes: set[str],
    build: Callable[[list[PopulationRecord], str, set[str]], B | None],
    warnings: list[str],
) -> tuple[B | None, list[PopulationRecord]]:
    """주거·직장인구 블록 하나와 그 분기의 서울 전체 행. 비는 이유는 warnings 에 적는다."""
    if rows is None:
        warnings.append(
            f"{label} 자료 파일을 읽지 못해 비워 두었습니다. 유동인구 분석에는 영향이 없습니다."
        )
        return None, []
    # 스냅샷은 한 분기만 담는다(write_snapshot). 유동인구보다 뒤처졌으면 갱신할 때라는 신호다.
    chosen, seoul = rows[0].stdr_yyqu_cd, rows
    if chosen != quarter:
        warnings.append(
            f"{label}는 {period_ko(quarter)} 자료가 없어 {period_ko(chosen)} 값을 썼습니다."
        )
    block = build(seoul, chosen, main_codes)
    if any(missing_fields(row, households=label == "주거인구") for row in seoul):
        warnings.append(f"{label} 자료에 결측 수치가 있어 관련 합계·비율은 null로 남겼습니다.")
    if block is None:
        warnings.append(f"반경과 겹치는 상권에 {label} 자료가 없습니다.")
    elif block.covered_trade_areas < block.trade_area_count:
        warnings.append(
            f"{label}는 상권 {block.trade_area_count}곳 중 {block.covered_trade_areas}곳에만 "
            "자료가 있어 그만큼만 합산했습니다."
            + (" 시장·역 상권은 주거인구가 없습니다." if label == "주거인구" else "")
        )
    return block, seoul


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
    radius = task.radius_m
    # 반경 안쪽 단계는 분석 반경보다 작은 것만 쓰고 분석 반경 자체를 마지막 점으로 둔다.
    profile_radii = tuple(sorted({r for r in settings.radius_profile_m if r < radius} | {radius}))
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
        # 반경별 곡선은 분석 반경 안쪽만 보므로 같은 상권 집합으로 충분하다.
        main_codes = {a.trdar_cd for a, _ in hits}
        series = await client.fetch_flpop_series(main_codes, settings.trend_quarters)
        quarter, latest = series[-1]
        records = [r for r in latest if r.trdar_cd in main_codes]
    except (httpx.TimeoutException, SeoulOpenApiTimeout):
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

    if all(
        len(missing_fields(record))
        == 3 + len(record.by_age) + len(record.by_time) + len(record.by_day)
        for record in records
    ):
        return empty(period_ko(quarter), "유동인구 수치가 모두 결측이라 분석할 수 없습니다.")

    population = _aggregate(records, quarter)
    # 분기 합계는 내보내지 않지만 규모 백분위를 낼 때는 필요하다(서울 기준선이 분기 합계
    # 기준으로 측정돼 있다). 계산에만 쓰고 `data` 에는 싣지 않는다.
    quarter_total = complete_sum(r.total for r in records)
    covered = len(records)
    type_result = classify(
        age_share=population.age_share,
        weekend_to_weekday=population.weekend_to_weekday_ratio,
    )
    reliability = _reliability(len(hits), covered)
    trend = _trend(series, main_codes)

    warnings = list(BASE_WARNINGS)
    incomplete = any(missing_fields(record) for _, rows in series for record in rows)
    if incomplete:
        warnings.append(
            "유동인구 자료에 결측 수치가 있어 해당 합계·비율을 null로 남기고 "
            "필요한 판정을 보류했습니다."
        )
    unnamed = [a.trdar_cd for a, _ in hits if not a.trdar_cd_nm]
    if unnamed:
        warnings.append(f"상권명이 없어 코드로 표시한 상권이 있습니다: {', '.join(unnamed)}")
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
    if covered == 1 and population.daily_avg is not None:
        warnings.append(
            f"반경 {radius}m 와 겹치는 상권이 1곳뿐이라(일평균 {population.daily_avg:,.0f}명) "
            "분포가 그 상권 하나에 좌우됩니다. 판정 신뢰도를 낮게 보십시오."
        )

    days = quarter_days(quarter)
    # 주거·직장인구는 API 가 아니라 패키지에 동봉한 스냅샷(data/*.csv)에서 읽는다 — 분기 필터가
    # 안 먹어 매번 약 73페이지를 받아야 했고, 값은 2~3년째 같다(population.py 참고).
    resident_rows, worker_rows = await asyncio.gather(
        asyncio.to_thread(_load, RESIDENT_KIND), asyncio.to_thread(_load, WORKER_KIND)
    )
    incomplete = incomplete or any(
        missing_fields(row, households=kind == RESIDENT_KIND)
        for kind, rows in ((RESIDENT_KIND, resident_rows), (WORKER_KIND, worker_rows))
        for row in rows or []
    )
    resident, resident_seoul = _population_block(
        "주거인구", resident_rows, quarter, main_codes, resident_block, warnings
    )
    worker, worker_seoul = _population_block(
        "직장인구", worker_rows, quarter, main_codes, worker_block, warnings
    )
    summary = (
        summary_block(latest, days, resident_seoul, worker_seoul, main_codes)
        if resident and worker
        else None
    )
    if resident and worker and resident.period_code != worker.period_code:
        warnings.append(
            f"주거인구({resident.period})와 직장인구({worker.period})의 분기가 달라 "
            "population_summary 의 비율은 서로 다른 분기를 나눈 값입니다."
        )

    data = FloatingPopulationData(
        description=_description(quarter, covered, outer_reach, radius),
        period_code=quarter,
        radius_m=radius,
        trade_areas=[
            TradeArea(
                code=a.trdar_cd,
                name=a.trdar_cd_nm or f"상권 {a.trdar_cd} (명칭 미제공)",
                kind=a.trdar_se_nm,
                adstrd=a.adstrd_nm,
                distance_m=round(d, 1),
                area_m2=round(a.relm_ar, 1),
                equivalent_radius_m=round(a.equivalent_radius_m, 1),
            )
            for a, d in hits
        ],
        population=population,
        benchmark=_benchmark(population, quarter_total, covered, days),
        trend=trend,
        radius_profile=_radius_profile(
            hits,
            {r.trdar_cd: r for r in latest},
            profile_radii,
            days,
        ),
        type=TypeJudgement(signals_unit="비율 (0~1). 주말/주중은 배수", **type_result.model_dump()),
        reliability=reliability,
        resident=resident,
        worker=worker,
        population_summary=summary,
        # 아래에서 선별 결과로 덮어씁니다.
        selection=Selection(
            applied=False,
            selectable=list(selection_rules.SELECTABLE),
            included=list(selection_rules.SELECTABLE),
            dropped=[],
        ),
        sources=[Source(**s, period=period_ko(quarter)) for s in SOURCES]
        + [
            Source(**s, period=b.period)
            for s, b in ((RESIDENT_SOURCE, resident), (WORKER_SOURCE, worker))
            if b
        ],
    )

    data.interpretation = interpret(data)

    # 기본은 자료 유무·비교 가능 분기 수로 선별하고, 주입한 함수가 있으면 사용합니다.
    selection, select_warning = await selection_rules._select(data, select)
    data.selection = selection
    # 원본 차트는 반환·저장하고 최종판단이 프롬프트 복사본에만 선별을 적용합니다.
    if select_warning:
        warnings.append(select_warning)

    return AgentAnalysis(
        request_id=task.request_id,
        agent_id=AGENT_ID,
        # 자료가 있는 상권이 반경 안 상권보다 적거나 주거·직장인구 파일을 못 읽었으면 "일부만
        # 확보" 다. 반경 안 상권에 주거인구가 원래 없는 것(시장·역)은 정상이라 ok + warnings.
        status=(
            "ok"
            if covered == len(hits)
            and resident_rows is not None
            and worker_rows is not None
            and not incomplete
            else "partial"
        ),
        scope=Scope(area=area_label, period=period_ko(quarter)),
        data=data.model_dump(mode="json"),
        error=None,
        warnings=warnings,
    )
