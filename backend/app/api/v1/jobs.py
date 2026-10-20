"""공개 API의 작업 등록·대기·진행 조회입니다."""

import asyncio
import os
from collections.abc import Coroutine

from fastapi import HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.db import repository
from app.schemas import DEFAULT_RADIUS_M, RadiusMeters
from app.services.jobs import JobClosedError, JobConflictError, JobLimitError

FINISHED = {"completed", "failed", "waiting_for_input"}
WAIT_QUERY = Query(
    default=True, description="false면 작업 ID를 즉시 반환하고 events로 진행을 조회합니다."
)


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address: str = Field(min_length=1, max_length=200)
    radius_m: RadiusMeters = DEFAULT_RADIUS_M
    allow_questions: StrictBool = False
    with_map: StrictBool = False
    floor: str | None = Field(default=None, pattern=r"^(지하 )?[1-9][0-9]{0,2}층$")
    exclusive_area_m2: float | None = Field(default=None, ge=0.01, le=100000, strict=True)


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
        repository.get_request_events,
        request_id,
        after=after,
        db_path=request.app.state.execution_settings.db_path,
    )
    if row is None:
        if request_id in jobs(request):
            return {
                "request_id": request_id,
                "status": "pending",
                "finished": False,
                "events": [],
                "next_after": after,
            }
        raise HTTPException(404, "분석 요청을 찾을 수 없습니다.")
    status = (
        "running" if request_id in jobs(request) and row["status"] in FINISHED else row["status"]
    )
    return {
        "request_id": request_id,
        "status": status,
        "finished": status in FINISHED,
        "events": events,
        "next_after": events[-1]["seq"] if events else after,
    }


def is_mock(requested):
    return requested or os.getenv("MOCK_MODE", "").lower() in {"1", "true", "yes"}
