import asyncio
import inspect
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any

from pydantic import ValidationError

from app.schemas import AgentAnalysis, AgentError, AgentId, AnalysisTask, Scope, Site

from .area_resolver import (
    BusinessArea,
    BusinessAreaNoDataError,
    BusinessAreaResolverError,
    resolve_area,
)
from .client import (
    FutureQuarterError,
    SeoulOpenAPIError,
    SeoulOpenAPINoDataError,
    detect_latest_valid_quarter,
    page_session,
)
from .config import Settings
from .formatter import BusinessLifecycleFormatterError, describe_industry, format_for_mediator
from .input_builder import build_agent_input
from .preprocess import UpstreamDataError


class BusinessLifecycleAgentError(RuntimeError):
    """개폐업 파이프라인 실행 오류입니다."""


AGENT_ID: AgentId = "business_lifecycle"


ResolveArea = Callable[[Site, Settings], BusinessArea]
RunPipeline = Callable[
    [str, str, int, str | None, str | None], dict[str, Any] | Awaitable[dict[str, Any]]
]


async def run_business_lifecycle_agent(
    area_code: str,
    base_quarter: str,
    quarter_count: int = 12,
    request_id: str | None = None,
    area_name: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Business Lifecycle 전체 파이프라인 실행.

    Open API
    → 전처리
    → 점수 계산
    → Agent Input
    → 관측 건수 설명
    """

    # ========================================================
    # 1. Agent Input 생성
    # ========================================================

    agent_input = await build_agent_input(
        area_code=area_code,
        base_quarter=base_quarter,
        quarter_count=quarter_count,
        request_id=request_id,
        area_name=area_name,
        settings=settings,
    )

    # ========================================================
    # 2. 점수가 있는 업종의 관측 건수를 설명
    # ========================================================

    scores = [describe_industry(industry) for industry in agent_input["industries"]]

    # ========================================================
    # 3. 최종 Agent 결과 생성
    # ========================================================

    result: dict[str, Any] = {
        "request_id": agent_input["request_id"],
        "agent_id": "business_lifecycle",
        "scope": agent_input["scope"],
        "coverage": agent_input["coverage"],
        "taxonomy": agent_input["taxonomy"],
        "scoring_method": agent_input["scoring_method"],
        "summary": (
            f"최근 {quarter_count}개 분기의 개폐업 자료로 {len(scores)}개 업종을 비교했습니다."
            if scores
            else "개폐업 관측 자료는 보존했으나 비교 가능한 자료가 부족해 상대 점수를 보류했습니다."
        ),
        "industry_scores": scores,
        # 데이터 부족으로 판단 보류
        "unavailable_industries": (agent_input["unavailable_industries"]),
    }

    return result


async def analyze(
    task: AnalysisTask | dict,
    settings: Settings | None = None,
    area_resolver: ResolveArea | None = None,
    run_pipeline: RunPipeline | None = None,
) -> AgentAnalysis:
    """팀 공통 인터페이스로 Business Lifecycle 분석을 실행합니다."""
    task = AnalysisTask.model_validate(task)
    try:
        settings = settings or Settings.from_env()
    except (ValueError, TypeError) as exc:
        return _error(task, "CONFIG_ERROR", exc)
    async with page_session(settings.request_timeout_s):
        return await _analyze(
            task,
            settings,
            area_resolver or resolve_area,
            run_pipeline or partial(_run_pipeline, settings=settings),
        )


async def _analyze(
    task: AnalysisTask,
    settings: Settings,
    area_resolver: ResolveArea,
    run_pipeline: RunPipeline,
) -> AgentAnalysis:
    site = task.site

    try:
        area = await asyncio.to_thread(
            _resolve_area,
            site=site,
            settings=settings,
            area_resolver=area_resolver,
        )
        base_quarter = await _choose_base_quarter(
            area_code=area.area_code,
            settings=settings,
        )
        call = partial(
            run_pipeline,
            area.area_code,
            base_quarter,
            settings.quarter_count,
            task.request_id,
            area.area_name,
        )
        agent_result: Any = (
            call() if inspect.iscoroutinefunction(run_pipeline) else await asyncio.to_thread(call)
        )
        if inspect.isawaitable(agent_result):
            agent_result = await agent_result
        return format_for_mediator(
            agent_result,
            scope_area=f"{area.area_name} ({area.area_code})",
            scope_period=_period_label(agent_result),
            metadata={
                "requested_radius_m": task.radius_m,
                "radius_applied": False,
                "area_code": area.area_code,
                "area_name": area.area_name,
                "area_type_code": area.area_type_code,
                "area_type_name": area.area_type_name,
                "district_code": area.district_code,
                "district_name": area.district_name,
                "dong_code": area.dong_code,
                "dong_name": area.dong_name,
                "base_quarter": base_quarter,
                "quarter_count": settings.quarter_count,
                "area_resolver": {
                    "method": (
                        "env_override" if _has_area_override(settings) else "official_polygon"
                    ),
                    "coordinate_system": "EPSG:5181",
                },
            },
            extra_warnings=[area.warning],
        )
    except BusinessAreaNoDataError:
        return _no_data(
            task=task,
            area=site.input_address,
            period="서울시 상권영역",
            warning="분석 가능한 상권을 찾지 못했습니다.",
        )
    except BusinessAreaResolverError as exc:
        return _error(task, "BusinessAreaResolverError", exc)
    except SeoulOpenAPINoDataError:
        return _no_data(
            task=task,
            area=site.input_address,
            period="서울시 최신 유효 분기",
            warning="조회된 개폐업 데이터가 없습니다.",
        )
    except FutureQuarterError as exc:
        return _error(task, "INVALID_INPUT", exc)
    except ValidationError:
        raise
    except UpstreamDataError as exc:
        return _error(task, "UPSTREAM_ERROR", exc)
    except ValueError as exc:
        return _error(task, "INVALID_INPUT", exc)
    except SeoulOpenAPIError as exc:
        return _error(task, "SeoulOpenAPIError", exc)
    except BusinessLifecycleAgentError as exc:
        return _error(task, "BusinessLifecycleAgentError", exc)
    except BusinessLifecycleFormatterError as exc:
        return _error(task, "BusinessLifecycleFormatterError", exc)
    except Exception as exc:  # noqa: BLE001
        return _error(task, "AGENT_FAILED", exc)


def _resolve_area(
    *,
    site: Site,
    settings: Settings,
    area_resolver: ResolveArea,
) -> BusinessArea:
    if settings.area_code_override or settings.area_name_override:
        if not settings.area_code_override or not settings.area_name_override:
            raise ValueError(
                "BUSINESS_LIFECYCLE_AREA_CODE와 BUSINESS_LIFECYCLE_AREA_NAME은 "
                "함께 설정해야 합니다."
            )
        return BusinessArea(
            area_code=settings.area_code_override,
            area_name=settings.area_name_override,
            area_type_code=None,
            area_type_name=None,
            district_code=None,
            district_name=None,
            dong_code=None,
            dong_name=None,
            x=0.0,
            y=0.0,
            warning="환경변수로 지정한 상권을 사용했습니다.",
        )

    return area_resolver(site, settings)


def _has_area_override(settings: Settings) -> bool:
    return bool(settings.area_code_override and settings.area_name_override)


async def _run_pipeline(
    area_code: str,
    base_quarter: str,
    quarter_count: int,
    request_id: str | None,
    area_name: str | None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    return await run_business_lifecycle_agent(
        area_code=area_code,
        base_quarter=base_quarter,
        quarter_count=quarter_count,
        request_id=request_id,
        area_name=area_name,
        settings=settings,
    )


async def _choose_base_quarter(
    area_code: str,
    settings: Settings,
) -> str:
    if settings.base_quarter_override:
        from .client import compare_quarters, latest_closed_quarter, validate_quarter_code

        validate_quarter_code(settings.base_quarter_override)
        if compare_quarters(settings.base_quarter_override, latest_closed_quarter()) > 0:
            raise FutureQuarterError(
                f"아직 확정되지 않은 분기는 조회하지 않습니다: {settings.base_quarter_override}"
            )
        return settings.base_quarter_override

    return await detect_latest_valid_quarter(
        area_code=area_code,
        candidate_count=settings.latest_quarter_search_count,
        settings=settings,
    )


def _period_label(agent_result: dict[str, Any]) -> str:
    scope = agent_result.get("scope", {})
    period = scope.get("period", {})
    if isinstance(period, dict):
        start = period.get("start_quarter")
        end = period.get("end_quarter")
        count = period.get("quarter_count")
        if start and end and count:
            return f"{start}~{end} ({count}개 분기)"
    base_quarter = scope.get("base_quarter")
    if base_quarter:
        return str(base_quarter)
    return "기준 기간 확인 불가"


def _no_data(
    *,
    task: AnalysisTask,
    area: str,
    period: str,
    warning: str,
) -> AgentAnalysis:
    return AgentAnalysis(
        request_id=task.request_id,
        agent_id=AGENT_ID,
        status="no_data",
        scope=Scope(area=area, period=period),
        warnings=[warning],
    )


def _error(
    task: AnalysisTask,
    code: str,
    _exc: BaseException,
) -> AgentAnalysis:
    return AgentAnalysis(
        request_id=task.request_id,
        agent_id=AGENT_ID,
        status="error",
        error=AgentError(
            code=code,
            message="개폐업 분석을 완료하지 못했습니다.",
        ),
    )
