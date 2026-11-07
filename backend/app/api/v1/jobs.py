"""공개 API의 작업 등록·대기·진행 조회입니다."""

import asyncio
from collections.abc import Coroutine
from typing import Literal

from fastapi import HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.application import requests as analysis_requests
from app.application.jobs import JobClosedError, JobConflictError, JobLimitError
from app.domain.schemas import DEFAULT_RADIUS_M, RadiusMeters

WAIT_QUERY = Query(
    default=True, description="false면 작업 ID를 즉시 반환하고 events로 진행을 조회합니다."
)


FacilityState = Literal["present", "installable", "unavailable"]


class Facilities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kitchen: FacilityState | None = None
    ventilation: FacilityState | None = None
    water_supply: FacilityState | None = None


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address: str = Field(min_length=1, max_length=200)
    radius_m: RadiusMeters = DEFAULT_RADIUS_M
    allow_questions: StrictBool = False
    with_map: StrictBool = False
    floor: str | None = Field(default=None, pattern=r"^(지하 )?[1-9][0-9]{0,2}층$")
    exclusive_area_m2: float | None = Field(default=None, ge=0.01, le=100000, strict=True)
    facilities: Facilities | None = None


def request_headers(request_id):
    return {"X-Request-ID": request_id}


def jobs(request):
    return request.app.state.job_registry.tasks


def start_task(request: Request, request_id: str, work: Coroutine) -> asyncio.Task:
    try:
        return request.app.state.job_registry.start(request_id, work)
    except JobConflictError:
        raise HTTPException(
            409, "이미 처리 중인 요청입니다.", headers=request_headers(request_id)
        ) from None
    except (JobLimitError, JobClosedError):
        raise HTTPException(
            429,
            "동시에 실행할 수 있는 분석 수를 넘었습니다.",
            headers=request_headers(request_id) | {"Retry-After": "30"},
        ) from None


async def await_task(task):
    return await task


def start_job(request, request_id, work):
    start_task(request, request_id, work)
    return JSONResponse(
        {"request_id": request_id, "status": "running"},
        status_code=202,
        headers=request_headers(request_id),
    )


async def health():
    return {"status": "ok"}


async def list_analysis_events(
    request_id: str, request: Request, after: int = Query(default=0, ge=0)
):
    row, events = await asyncio.to_thread(
        request.app.state.services.requests.events, request_id, after=after
    )
    view = analysis_requests.progress_view(
        request_id, row, events, after=after, running=request_id in jobs(request)
    )
    if view is None:
        raise HTTPException(404, analysis_requests.NOT_FOUND)
    return view
