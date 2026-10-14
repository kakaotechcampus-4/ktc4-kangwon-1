"""단일 도구 루프를 공개 API에 연결합니다. 옛 라우터는 등록하지 않습니다."""

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field

from app.db.connection import connect
from app.schemas import DecisionResult, Schema, Text
from app.services.analysis import execute_agentic_analysis, resume_agentic_analysis
from app.services.mock import dependencies, generators

from .errors import run_or_http
from .jobs import (
    WAIT_QUERY,
    AnalysisRequest,
    await_task,
    health,
    jobs,
    list_analysis_events,
    request_headers,
    start_job,
    start_task,
)
from .responses import AcceptedAnalysis, AnalysisEvents

router = APIRouter(prefix="/api/v1", tags=["analysis"])
router.add_api_route("/health", health, methods=["GET"])
router.add_api_route(
    "/analyses/{request_id}/events",
    list_analysis_events,
    methods=["GET"],
    response_model=AnalysisEvents,
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


def is_mock(requested):
    return requested or os.getenv("MOCK_MODE", "").lower() in {"1", "true", "yes"}


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
)
async def create_analysis(
    body: AnalysisRequest,
    request: Request,
    response: Response,
    runner: Annotated[Any, Depends(analysis_runner)],
    mock: bool = False,
    wait: bool = WAIT_QUERY,
):
    if not body.address.strip():
        raise HTTPException(400, "주소를 입력해 주세요.")
    request_id = uuid.uuid4().hex
    response.headers.update(request_headers(request_id))

    async def work():
        outcome = await runner(
            body.address,
            request_id=request_id,
            radius_m=body.radius_m,
            allow_questions=body.allow_questions,
            **options(request, request_id),
            **(dependencies(ask=body.allow_questions) if is_mock(mock) else {}),
        )
        return public_result(request_id, outcome)

    if not wait:
        return start_job(request, request_id, work())
    return await run_or_http(
        await_task(start_task(request, request_id, work())), request_id, kind="analysis"
    )


def detail(request_id, path):
    with connect(path) as db:
        row = db.execute(
            "SELECT * FROM analysis_requests WHERE request_id=?", (request_id,)
        ).fetchone()
        if row is None:
            return None
        output = dict(row)
        for field in ("site", "result", "error"):
            output[field] = (
                json.loads(output.pop(field + "_json")) if row[field + "_json"] else None
            )
        question = db.execute(
            "SELECT * FROM agentic_questions WHERE request_id=?", (request_id,)
        ).fetchone()
        output["questions"] = (
            {
                "question_session_id": question["question_session_id"],
                "questions": json.loads(question["questions_json"]),
                "status": question["status"],
            }
            if question
            else None
        )
        report = db.execute(
            "SELECT rendered_json FROM agentic_reports WHERE report_id=?",
            ((output["result"] or {}).get("report_id"),),
        ).fetchone()
        output["rendered"] = json.loads(report[0]) if report else None
        if output["result"] is not None:
            output["result"] = DecisionResult.model_validate(output["result"]).model_dump(
                mode="json"
            )
        return output


@router.get("/analyses/{request_id}")
async def get_analysis(request_id: str, request: Request):
    result = await asyncio.to_thread(
        detail, request_id, request.app.state.execution_settings.db_path
    )
    if result is None:
        raise HTTPException(404, "분석 요청을 찾을 수 없습니다.")
    return result


@router.post(
    "/analyses/{request_id}/answers",
    response_model=DecisionResult | Waiting,
    responses={202: {"model": AcceptedAnalysis}},
)
async def answers(
    request_id: str,
    body: Answers,
    request: Request,
    runner: Annotated[Any, Depends(resume_runner)],
    mock: bool = False,
    wait: bool = WAIT_QUERY,
):
    row = await asyncio.to_thread(detail, request_id, request.app.state.execution_settings.db_path)
    if row is None:
        raise HTTPException(404, "분석 요청을 찾을 수 없습니다.")
    question = row["questions"]
    if (
        request_id in jobs(request)
        or row["status"] != "waiting_for_input"
        or not question
        or question["question_session_id"] != body.question_session_id
    ):
        raise HTTPException(409, "현재 대기 중인 질문 세션이 아닙니다.")
    if set(body.answers) != {q["field"] for q in question["questions"]}:
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
