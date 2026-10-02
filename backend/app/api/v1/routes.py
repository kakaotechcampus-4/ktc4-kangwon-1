"""사용자 요청을 받아 분석 흐름을 실행하는 v1 API입니다."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.address import GeocodeError
from app.agents.orchestration.workflow import build_supplement_tools
from app.db import repository
from app.logging import log_exception
from app.schemas import (
    DEFAULT_RADIUS_M,
    AnswerSubmission,
    DecisionResult,
    RadiusMeters,
    WaitingForInput,
    normalize_answers,
)
from app.services.analysis import (
    AnalysisAlreadyFailedError,
    AnalysisAlreadyRunningError,
    execute_analysis,
    resume_analysis,
    retry_decision,
)
from app.services.mocking import mock_dependencies
from app.services.views import analysis_detail

from .responses import AcceptedAnalysis, AnalysisDetail, AnalysisEvents

router = APIRouter(prefix="/api/v1", tags=["analysis"])
logger = logging.getLogger(__name__)
FINISHED = {"completed", "failed", "waiting_for_input"}
WAIT_QUERY = Query(
    default=True,
    description="false면 202와 request_id를 바로 돌려주고 백그라운드에서 실행합니다. "
    "진행은 GET /analyses/{request_id}/events로 확인합니다.",
)


def _log_unexpected(request_id: str, exc: Exception) -> None:
    # 예외 원문·연쇄 예외에는 외부 응답이나 사용자 입력이 섞일 수 있습니다.
    log_exception(logger, "예상 못 한 오류: request_id=%s", exc, request_id)


def _jobs(request: Request) -> dict[str, asyncio.Task]:
    return request.app.state.__dict__.setdefault("jobs", {})


def _start_job(request: Request, request_id: str, work: Coroutine) -> JSONResponse:
    """분석을 백그라운드 작업으로 등록하고 바로 202를 돌려줍니다."""
    # ponytail: 프로세스 안 작업표입니다. 서버를 여러 대 띄우면 외부 큐가 필요합니다.
    jobs = _jobs(request)
    if len(jobs) >= request.app.state.execution_settings.max_concurrency:
        work.close()
        raise HTTPException(
            429,
            "동시에 실행할 수 있는 분석 수를 넘었습니다. 잠시 뒤 다시 요청해 주세요.",
            headers={"X-Request-ID": request_id, "Retry-After": "30"},
        )
    task = asyncio.create_task(work, name="analysis-" + request_id)
    jobs[request_id] = task

    def finished(done: asyncio.Task) -> None:
        jobs.pop(request_id, None)
        if not done.cancelled() and done.exception() is not None:
            # 실패 상태와 이벤트는 서비스 계층이 DB에 남깁니다. 여기서는 로그만 씁니다.
            logger.warning("백그라운드 분석 실패: %s", request_id, exc_info=done.exception())

    task.add_done_callback(finished)
    return JSONResponse(
        {"request_id": request_id, "status": "running"},
        status_code=202,
        headers=_request_headers(request_id),
    )


class AnalysisRequest(BaseModel):
    """분석 요청 본문입니다."""

    model_config = ConfigDict(extra="forbid")
    radius_m: RadiusMeters = DEFAULT_RADIUS_M
    allow_questions: StrictBool = False
    with_map: StrictBool = False

    address: str = Field(
        min_length=1,
        max_length=200,
        description="분석할 공실의 주소. 상세주소가 붙어 있어도 됩니다.",
        examples=["서울특별시 노원구 한글비석로 242 삼부프라자 1층"],
    )


def _mock_enabled(requested: bool) -> bool:
    return requested or os.getenv("MOCK_MODE", "").strip().lower() in {"1", "true", "yes"}


def analysis_runner():
    return execute_analysis


def resume_runner():
    return resume_analysis


def retry_runner():
    return retry_decision


class DecisionRetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    failed_at: str = Field(min_length=1, max_length=100)


@router.get("/health", summary="상태 확인")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/analyses",
    response_model=DecisionResult | WaitingForInput,
    responses={202: {"model": AcceptedAnalysis}},
    response_model_exclude_none=True,
    summary="주소 하나로 업종 추천 리포트를 만듭니다",
)
async def create_analysis(
    body: AnalysisRequest,
    request: Request,
    response: Response,
    runner: Annotated[Any, Depends(analysis_runner)],
    mock: bool = Query(
        default=False,
        description="외부 API·모델 호출 없이 고정 응답을 돌려줍니다. 화면 연동용입니다.",
    ),
    wait: bool = WAIT_QUERY,
) -> Any:
    """주소 준비부터 최종판단 또는 선택적 질문 대기까지 실행합니다.

    `mock=true`이거나 `MOCK_MODE` 환경변수가 켜져 있으면 외부 호출 없이
    같은 형태의 고정 응답을 돌려줍니다. 키가 없어도 화면을 붙일 수 있습니다.
    """
    if not body.address.strip():
        raise HTTPException(status_code=400, detail="주소를 입력해 주세요.")
    request_id = uuid.uuid4().hex
    headers = _request_headers(request_id)
    response.headers.update(headers)
    if _mock_enabled(mock):
        work = runner(
            body.address,
            settings=request.app.state.execution_settings,
            request_id=request_id,
            radius_m=body.radius_m,
            allow_questions=body.allow_questions,
            **mock_dependencies(
                "analysis",
                with_map=body.with_map,
                allow_questions=body.allow_questions,
                evaluators_enabled=request.app.state.execution_settings.evaluators_enabled,
            ),
        )
    else:
        from app.agents.map_analysis.agent import observe

        work = runner(
            body.address,
            settings=request.app.state.execution_settings,
            request_id=request_id,
            radius_m=body.radius_m,
            allow_questions=body.allow_questions,
            map_lookup=observe if body.with_map else None,
            supplements=build_supplement_tools(request.app.state.execution_settings),
        )
    if not wait:
        return _start_job(request, request_id, work)
    return await _run_or_http(work, request_id, kind="analysis")


@router.get(
    "/analyses/{request_id}/events",
    response_model=AnalysisEvents,
    summary="진행 이벤트를 순번 이후부터 조회합니다 (진행 화면 폴링용)",
)
async def list_analysis_events(
    request_id: str,
    request: Request,
    after: int = Query(default=0, ge=0, description="이미 받은 마지막 seq"),
) -> dict[str, Any]:
    path = request.app.state.execution_settings.db_path
    row = await asyncio.to_thread(repository.get_request, request_id, db_path=path)
    if row is None:
        # 202 직후에는 백그라운드 작업이 아직 요청을 저장하기 전일 수 있습니다.
        if request_id in _jobs(request):
            return {
                "request_id": request_id,
                "status": "pending",
                "finished": False,
                "events": [],
                "next_after": after,
            }
        raise HTTPException(404, "분석 요청을 찾을 수 없습니다.")
    events = await asyncio.to_thread(repository.list_events, request_id, after=after, db_path=path)
    # 답변 재개 직후처럼 DB 상태가 아직 바뀌기 전이어도 작업이 살아 있으면 진행 중입니다.
    active = request_id in _jobs(request)
    status = "running" if active and row["status"] in FINISHED else row["status"]
    return {
        "request_id": request_id,
        "status": status,
        "finished": status in FINISHED,
        "events": events,
        "next_after": events[-1]["seq"] if events else after,
    }


@router.get(
    "/analyses/{request_id}",
    response_model=AnalysisDetail,
    response_model_exclude_unset=True,
    summary="저장된 분석 상태와 결과를 조회합니다",
)
async def get_analysis(request_id: str, request: Request) -> dict[str, Any]:
    try:
        row = await analysis_detail(request_id, request.app.state.execution_settings.db_path)
        if row is not None:
            return row
    except ValueError as exc:
        logger.error("저장 자료 손상: request_id=%s", request_id)
        raise HTTPException(status_code=500, detail="저장된 분석 조회에 실패했습니다.") from exc
    except Exception as exc:
        _log_unexpected(request_id, exc)
        raise HTTPException(status_code=500, detail="저장된 분석 조회에 실패했습니다.") from exc
    raise HTTPException(status_code=404, detail="분석 요청을 찾을 수 없습니다.")


@router.post(
    "/analyses/{request_id}/answers",
    response_model=DecisionResult,
    responses={202: {"model": AcceptedAnalysis}},
    response_model_exclude_none=True,
    summary="답변을 제출하고 최종판단을 재개합니다",
)
async def submit_answers(
    request_id: str,
    body: AnswerSubmission,
    request: Request,
    response: Response,
    runner: Annotated[Any, Depends(resume_runner)],
    mock: bool = False,
    wait: bool = WAIT_QUERY,
):
    headers = _request_headers(request_id)
    response.headers.update(headers)
    if request_id != body.request_id:
        raise HTTPException(422, "경로와 본문의 요청 ID가 다릅니다.", headers=headers)
    path = request.app.state.execution_settings.db_path

    async def work():
        row = await asyncio.to_thread(repository.get_request, request_id, db_path=path)
        if row is None:
            raise HTTPException(404, "분석 요청을 찾을 수 없습니다.", headers=headers)
        snapshot = await asyncio.to_thread(
            repository.get_question_snapshot, request_id, db_path=path
        )
        if snapshot is None:
            raise HTTPException(409, "질문 대기 기록이 없습니다.", headers=headers)
        try:
            normalized = normalize_answers(snapshot.waiting, body)
        except ValueError:
            raise HTTPException(
                409, "질문 ID 또는 답변 항목이 일치하지 않습니다.", headers=headers
            ) from None
        previous = await asyncio.to_thread(
            repository.get_question_answers, request_id, db_path=path
        )
        if previous is not None and previous != normalized:
            raise HTTPException(409, "이미 제출한 답변은 변경할 수 없습니다.", headers=headers)
        work = runner(
            normalized,
            settings=request.app.state.execution_settings,
            **(mock_dependencies("resume") if _mock_enabled(mock) else {"generate": None}),
        )
        if not wait:
            return _start_job(request, request_id, work)
        return await work

    return await _run_or_http(work(), request_id, kind="answers")


@router.post(
    "/analyses/{request_id}/retry-decision",
    response_model=DecisionResult,
    summary="저장된 자료로 실패한 최종판단만 재시도합니다",
)
async def retry_analysis_decision(
    request_id: str,
    body: DecisionRetryRequest,
    request: Request,
    runner: Annotated[Any, Depends(retry_runner)],
    mock: bool = False,
):
    headers = _request_headers(request_id)

    async def work():
        if (
            await asyncio.to_thread(
                repository.get_request,
                request_id,
                db_path=request.app.state.execution_settings.db_path,
            )
            is None
        ):
            raise HTTPException(404, "분석 요청을 찾을 수 없습니다.", headers=headers)
        return await runner(
            request_id,
            failed_at=body.failed_at,
            settings=request.app.state.execution_settings,
            **(mock_dependencies("retry") if _mock_enabled(mock) else {"generate": None}),
        )

    return await _run_or_http(work(), request_id, kind="retry")


async def _run_or_http(work: Coroutine, request_id: str, *, kind: str):
    """세 POST 경로의 오류를 기존 상태 코드와 문구로 변환합니다."""
    headers = _request_headers(request_id)
    try:
        return await work
    except Exception as exc:
        if isinstance(exc, HTTPException) and kind != "analysis":
            raise
        if kind == "analysis" and isinstance(exc, GeocodeError):
            invalid = exc.code in {
                "EMPTY_ADDRESS",
                "NOT_FOUND",
                "ADDRESS_AMBIGUOUS",
                "ADDRESS_MISMATCH",
            }
            raise HTTPException(
                400 if invalid else 502,
                "주소를 확인해 주세요." if invalid else "주소 조회 서비스에 실패했습니다.",
                headers=headers,
            ) from exc
        if kind == "answers" and isinstance(
            exc,
            (
                AnalysisAlreadyRunningError,
                AnalysisAlreadyFailedError,
                repository.AnswerConflictError,
            ),
        ):
            raise HTTPException(
                409, "이미 처리 중이거나 실패한 답변입니다. 상태를 조회하세요.", headers=headers
            ) from None
        if kind == "retry" and isinstance(exc, repository.DecisionRetryConflictError):
            raise HTTPException(
                409, "재시도할 실패 상태·저장 자료를 확인하세요.", headers=headers
            ) from None
        if isinstance(exc, (RuntimeError, TimeoutError)):
            message = (
                "외부 분석 서비스에 실패했습니다."
                if kind == "analysis"
                else "최종판단 서비스에 실패했습니다."
            )
            error = HTTPException(502, message, headers=headers)
        else:
            _log_unexpected(request_id, exc)
            messages = {
                "analysis": "분석 결과 처리 또는 저장에 실패했습니다.",
                "answers": "답변 처리 또는 저장에 실패했습니다.",
                "retry": "최종판단 검증 또는 저장에 실패했습니다.",
            }
            error = HTTPException(500, messages[kind], headers=headers)
        if kind == "analysis":
            raise error from exc
        raise error from None


def _request_headers(request_id: str) -> dict[str, str]:
    return {"X-Request-ID": request_id}
