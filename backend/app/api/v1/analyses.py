"""단일 도구 루프를 공개 API에 연결합니다. 옛 라우터는 등록하지 않습니다."""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import Field

from app.db.connection import connect
from app.db.repository import create_request
from app.schemas import DecisionResult, FactView, Schema, Text
from app.services.analysis import execute_agentic_analysis, resume_agentic_analysis
from app.services.mock import dependencies, generators

from .errors import run_or_http
from .jobs import (
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


class RequestFacts(Schema):
    request_id: Text
    snapshot_id: Text | None
    facts: list[FactView]


def request_facts(request_id, path):
    """리포트 차트용으로 요청 스냅샷의 전체 fact를 읽습니다. 보고서 인용 여부와 무관합니다."""
    with connect(path) as db:
        if not db.execute(
            "SELECT 1 FROM analysis_requests WHERE request_id=?", (request_id,)
        ).fetchone():
            return None
        snapshot = db.execute(
            "SELECT snapshot_id FROM snapshots WHERE request_id=?", (request_id,)
        ).fetchone()
        if snapshot is None:
            return RequestFacts(request_id=request_id, snapshot_id=None, facts=[])
        snapshot_id = snapshot["snapshot_id"]
        local = db.execute(
            "SELECT scope_json FROM local_snapshots WHERE snapshot_id=?", (snapshot_id,)
        ).fetchone()
        rows = db.execute(
            "SELECT *,EXISTS(SELECT 1 FROM local_fact_lineage l WHERE l.fact_id=facts.fact_id) "
            "AS local_lineage FROM facts WHERE request_id=? AND snapshot_id=? "
            # 공간 비교는 답변마다 새로 만들어지므로 현재 판정만 돌려줍니다.
            "AND (metric!='space_fit' OR fact_id IN (SELECT fact_id FROM space_fit_current "
            "WHERE request_id=? AND snapshot_id=?)) ORDER BY source,metric,industry_code,fact_id",
            (request_id, snapshot_id, request_id, snapshot_id),
        ).fetchall()
    # 로컬 자료 fact의 공간 범위는 스냅샷에 한 번만 저장되어 있어 읽을 때 펼칩니다.
    spatial = json.loads(local["scope_json"]) | {"snapshot_id": snapshot_id} if local else None
    facts = [
        FactView(
            fact_id=r["fact_id"],
            source=r["source"],
            metric=r["metric"],
            value=json.loads(r["value_json"]),
            unit=r["unit"],
            period=r["period"],
            spatial_scope=spatial
            if r["local_lineage"] and spatial
            else json.loads(r["spatial_scope_json"]),
            industry_code=r["industry_code"],
            status="not_applicable" if r["status"] == "n.a." else r["status"],
            citable=bool(r["citable"]),
            calc_version=r["calc_version"],
            provenance_ref=(
                "fact_parents:"
                if r["metric"] == "space_fit"
                else "local_fact_lineage:"
                if r["local_lineage"]
                else "fact_sources:"
            )
            + r["fact_id"],
        )
        for r in rows
    ]
    return RequestFacts(request_id=request_id, snapshot_id=snapshot_id, facts=facts)


@router.get("/analyses/{request_id}/facts", response_model=RequestFacts)
async def get_analysis_facts(request_id: str, request: Request):
    result = await asyncio.to_thread(
        request_facts, request_id, request.app.state.execution_settings.db_path
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
