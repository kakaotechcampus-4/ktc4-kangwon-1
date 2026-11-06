"""단일 도구 루프를 공개 API에 연결합니다. 옛 라우터는 등록하지 않습니다."""

import asyncio
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import Field

from app.api.v1.deps import optional_user, require_origin, verified_user
from app.api.v1.errors import run_or_http
from app.api.v1.jobs import (
    WAIT_QUERY,
    AnalysisRequest,
    await_task,
    health,
    is_mock,
    jobs,
    list_analysis_events,
    request_headers,
    start_job,
    start_task,
)
from app.api.v1.responses import AcceptedAnalysis, AnalysisEvents, RequestFacts, StoredAnalysis
from app.db.repository import (
    create_request,
    get_analysis_detail,
    get_answer_gate,
    list_snapshot_facts,
    owner_of,
)
from app.schemas import DecisionResult, Schema, Text
from app.services.analysis import execute_agentic_analysis, resume_agentic_analysis
from app.services.mock import dependencies, generators

router = APIRouter(prefix="/api/v1", tags=["analysis"])
router.add_api_route("/health", health, methods=["GET"])

NOT_FOUND = "분석 요청을 찾을 수 없습니다."


async def require_owner(
    request_id: str,
    request: Request,
    user: Annotated[dict[str, Any] | None, Depends(optional_user)],
) -> None:
    """남의 요청은 404로 가립니다. 403이면 그 ID가 있다는 사실이 새 나갑니다."""
    owner = await asyncio.to_thread(
        owner_of, request_id, db_path=request.app.state.execution_settings.db_path
    )
    if owner is None:
        raise HTTPException(404, NOT_FOUND)
    # 인증을 붙이기 전에 쌓인 요청은 소유자가 없습니다. 그 자료만 열어 둡니다.
    if owner == "legacy":
        return
    if user is None or user["user_id"] != owner:
        raise HTTPException(404, NOT_FOUND)


# 진행 이벤트는 함수로 등록돼 있어 데코레이터 대신 dependencies 인자로 가드를 겁니다.
router.add_api_route(
    "/analyses/{request_id}/events",
    list_analysis_events,
    methods=["GET"],
    response_model=AnalysisEvents,
    dependencies=[Depends(require_owner)],
)


class Waiting(Schema):
    request_id: Text
    status: Literal["waiting_for_input"] = "waiting_for_input"
    question_session_id: Text
    questions: list[dict[str, str]]


class Answers(Schema):
    question_session_id: Text
    answers: dict[str, Annotated[str, Field(min_length=1, max_length=500)]]


def analysis_runner():
    return execute_agentic_analysis


def resume_runner():
    return resume_agentic_analysis


def options(request, request_id):
    directory = getattr(request.app.state, "recording_dir", None)
    return {
        "db_path": request.app.state.execution_settings.db_path,
        "recording_path": Path(directory) / f"{request_id}-model-calls.json" if directory else None,
        "measurement": request.app.state.measurement,
    }


def space_answers(body):
    values = {}
    if body.floor is not None:
        values["floor"] = body.floor
    if body.exclusive_area_m2 is not None:
        values["exclusive_area"] = f"{body.exclusive_area_m2:.2f}".rstrip("0").rstrip(".") + "㎡"
    if body.facilities is not None:
        facilities = body.facilities.model_dump(exclude_none=True)
        if facilities:
            values["existing_facilities"] = facilities
    return values or None


def public_result(request_id, outcome):
    if outcome.status == "waiting_for_input":
        return Waiting(
            request_id=request_id,
            question_session_id=outcome.question_session_id,
            questions=[q.model_dump(mode="json") for q in outcome.questions],
        )
    return DecisionResult.model_validate(outcome.result.model_dump(mode="json"))


@router.post(
    "/analyses",
    response_model=DecisionResult | Waiting,
    responses={202: {"model": AcceptedAnalysis}},
    dependencies=[Depends(require_origin)],
)
async def create_analysis(
    body: AnalysisRequest,
    request: Request,
    response: Response,
    runner: Annotated[Any, Depends(analysis_runner)],
    user: Annotated[dict[str, Any], Depends(verified_user)],
    mock: bool = False,
    wait: bool = WAIT_QUERY,
):
    if not body.address.strip():
        raise HTTPException(400, "주소를 입력해 주세요.")
    request_id = uuid.uuid4().hex
    response.headers.update(request_headers(request_id))
    ready = asyncio.Event()

    async def work():
        await ready.wait()
        outcome = await runner(
            body.address,
            request_id=request_id,
            radius_m=body.radius_m,
            allow_questions=body.allow_questions,
            confirmed_space=space_answers(body),
            request_prepared=True,
            **options(request, request_id),
            **(dependencies(ask=body.allow_questions) if is_mock(mock) else {}),
        )
        return public_result(request_id, outcome)

    # 슬롯을 먼저 확보하고 저장이 끝난 뒤 분석을 시작해 429와 초기 GET을 함께 보장합니다.
    task = start_task(request, request_id, work())
    try:
        await asyncio.to_thread(
            create_request,
            request_id,
            body.address,
            radius_m=body.radius_m,
            user_id=user["user_id"],
            db_path=request.app.state.execution_settings.db_path,
        )
    except BaseException:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise
    ready.set()
    if not wait:
        return JSONResponse(
            {"request_id": request_id, "status": "pending"},
            status_code=202,
            headers=request_headers(request_id),
        )
    return await run_or_http(await_task(task), request_id, kind="analysis")


@router.get(
    "/analyses/{request_id}",
    response_model=StoredAnalysis,
    dependencies=[Depends(require_owner)],
)
async def get_analysis(request_id: str, request: Request):
    stored = await asyncio.to_thread(
        get_analysis_detail, request_id, db_path=request.app.state.execution_settings.db_path
    )
    if stored is None:
        raise HTTPException(404, NOT_FOUND)
    return stored


@router.get(
    "/analyses/{request_id}/facts",
    response_model=RequestFacts,
    dependencies=[Depends(require_owner)],
)
async def get_analysis_facts(request_id: str, request: Request):
    found = await asyncio.to_thread(
        list_snapshot_facts, request_id, db_path=request.app.state.execution_settings.db_path
    )
    if found is None:
        raise HTTPException(404, NOT_FOUND)
    return RequestFacts(request_id=request_id, snapshot_id=found.snapshot_id, facts=found.facts)


@router.post(
    "/analyses/{request_id}/answers",
    response_model=DecisionResult | Waiting,
    responses={202: {"model": AcceptedAnalysis}},
    dependencies=[Depends(require_origin), Depends(require_owner)],
)
async def answers(
    request_id: str,
    body: Answers,
    request: Request,
    runner: Annotated[Any, Depends(resume_runner)],
    user: Annotated[dict[str, Any], Depends(verified_user)],
    mock: bool = False,
    wait: bool = WAIT_QUERY,
):
    gate = await asyncio.to_thread(
        get_answer_gate, request_id, db_path=request.app.state.execution_settings.db_path
    )
    if gate is None:
        raise HTTPException(404, NOT_FOUND)
    # 질문 행이 없으면 question_session_id 가 None 이라 아래 비교에서 걸립니다.
    if (
        request_id in jobs(request)
        or gate.status != "waiting_for_input"
        or gate.question_session_id != body.question_session_id
    ):
        raise HTTPException(409, "현재 대기 중인 질문 세션이 아닙니다.")
    if set(body.answers) != gate.fields:
        raise HTTPException(422, "질문 항목과 답변 항목이 다릅니다.")

    async def work():
        outcome = await runner(
            request_id,
            body.answers,
            **options(request, request_id),
            **(generators() if is_mock(mock) else {}),
        )
        return public_result(request_id, outcome)

    if not wait:
        return start_job(request, request_id, work())
    return await run_or_http(
        await_task(start_task(request, request_id, work())), request_id, kind="answers"
    )
