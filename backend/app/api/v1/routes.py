"""사용자 요청을 받아 분석 흐름을 실행하는 v1 API입니다."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.address import GeocodeError
from app.agents.orchestration.workflow import build_supplement_tools
from app.db import repository
from app.mocks import mock_agents, mock_generate, mock_resolve
from app.schemas import (
    AGENT_IDS,
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

from .mock import interactive_decision, map_observation, specialist

router = APIRouter(prefix="/api/v1", tags=["analysis"])


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
) -> DecisionResult | WaitingForInput:
    """주소 준비부터 최종판단 또는 선택적 질문 대기까지 실행합니다.

    `mock=true`이거나 `MOCK_MODE` 환경변수가 켜져 있으면 외부 호출 없이
    같은 형태의 고정 응답을 돌려줍니다. 키가 없어도 화면을 붙일 수 있습니다.
    """
    if not body.address.strip():
        raise HTTPException(status_code=400, detail="주소를 입력해 주세요.")
    request_id = uuid.uuid4().hex
    headers = {"X-Request-ID": request_id}
    response.headers.update(headers)
    try:
        if _mock_enabled(mock):
            return await runner(
                body.address,
                settings=request.app.state.execution_settings,
                request_id=request_id,
                resolve=mock_resolve,
                agents=mock_agents(),
                generate_specialists=dict.fromkeys((*AGENT_IDS, "map_analysis"), specialist),
                radius_m=body.radius_m,
                allow_questions=body.allow_questions,
                map_lookup=map_observation if body.with_map else None,
                generate=interactive_decision(with_map=body.with_map, allow_questions=True)
                if body.allow_questions or body.with_map
                else mock_generate,
            )
        from app.agents.map_analysis.agent import observe

        return await runner(
            body.address,
            settings=request.app.state.execution_settings,
            request_id=request_id,
            radius_m=body.radius_m,
            allow_questions=body.allow_questions,
            map_lookup=observe if body.with_map else None,
            supplements=build_supplement_tools(request.app.state.execution_settings),
        )
    except GeocodeError as exc:
        invalid = exc.code in {
            "EMPTY_ADDRESS",
            "NOT_FOUND",
            "ADDRESS_AMBIGUOUS",
            "ADDRESS_MISMATCH",
        }
        raise HTTPException(
            status_code=400 if invalid else 502,
            detail="주소를 확인해 주세요." if invalid else "주소 조회 서비스에 실패했습니다.",
            headers=headers,
        ) from exc
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(
            status_code=502, detail="외부 분석 서비스에 실패했습니다.", headers=headers
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="분석 결과 처리 또는 저장에 실패했습니다.", headers=headers
        ) from exc


@router.get("/analyses/{request_id}", summary="저장된 분석 상태와 결과를 조회합니다")
async def get_analysis(request_id: str, request: Request) -> dict[str, Any]:
    try:
        row = await asyncio.to_thread(
            repository.get_request, request_id, db_path=request.app.state.execution_settings.db_path
        )
        if row is not None:
            row.pop("execution_json", None)
            if row["analysis_mode"] == "multi_agent":
                state = await asyncio.to_thread(
                    repository.get_deliberation,
                    request_id,
                    db_path=request.app.state.execution_settings.db_path,
                )
                row["deliberation"] = {
                    "briefs": [b.model_dump(mode="json") for b in state["briefs"]],
                    "answers": [
                        a.model_dump(mode="json", exclude={"analysis", "map_observation"})
                        for a in state["specialist_answers"]
                    ],
                    "consult_round": state["consult_round"],
                    "map_attempt": state["map_attempt"],
                    "budget": state["execution"].get("budget", {"used": 0, "calls": []}),
                    "elapsed_seconds": state["execution"].get("elapsed_seconds", 0),
                }
            # 과거 업종명·스키마는 저장 당시 값 그대로 반환합니다.
            for name in ("site", "result", "error"):
                value = row.pop(f"{name}_json")
                row[name] = json.loads(value) if value is not None else None
            row.update(
                await asyncio.to_thread(
                    _details, request_id, request.app.state.execution_settings.db_path
                )
            )
            return row
    except Exception as exc:
        raise HTTPException(status_code=500, detail="저장된 분석 조회에 실패했습니다.") from exc
    raise HTTPException(status_code=404, detail="분석 요청을 찾을 수 없습니다.")


def _details(request_id, db_path):
    snapshot = repository.get_question_snapshot(request_id, db_path=db_path)
    mapped = repository.get_map_lookup(request_id, db_path=db_path)
    return {
        "decision_failures": repository.list_decision_failures(request_id, db_path=db_path),
        "questions": snapshot.waiting.model_dump(mode="json") if snapshot else None,
        "analyses": [
            {"attempt": r["attempt"], "analysis": json.loads(r["analysis_json"])}
            for r in repository.list_agent_results(request_id, db_path=db_path)
        ],
        "supplements": [
            json.loads(r["event_json"])
            for r in repository.list_supplement_events(request_id, db_path=db_path)
        ],
        "map_status": mapped["status"] if mapped else None,
        "map_observation": mapped["observation"] if mapped else None,
    }


@router.post(
    "/analyses/{request_id}/answers",
    response_model=DecisionResult,
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
):
    headers = {"X-Request-ID": request_id}
    response.headers.update(headers)
    if request_id != body.request_id:
        raise HTTPException(422, "경로와 본문의 요청 ID가 다릅니다.", headers=headers)
    path = request.app.state.execution_settings.db_path
    try:
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
        return await runner(
            normalized,
            settings=request.app.state.execution_settings,
            generate=mock_generate if _mock_enabled(mock) else None,
            **(
                {
                    "generate_specialists": dict.fromkeys((*AGENT_IDS, "map_analysis"), specialist),
                    "map_lookup": map_observation,
                    "supplements": [],
                }
                if _mock_enabled(mock)
                else {}
            ),
        )
    except HTTPException:
        raise
    except (
        AnalysisAlreadyRunningError,
        AnalysisAlreadyFailedError,
        repository.AnswerConflictError,
    ):
        raise HTTPException(
            409, "이미 처리 중이거나 실패한 답변입니다. 상태를 조회하세요.", headers=headers
        ) from None
    except (RuntimeError, TimeoutError):
        raise HTTPException(502, "최종판단 서비스에 실패했습니다.", headers=headers) from None
    except Exception:
        raise HTTPException(500, "답변 처리 또는 저장에 실패했습니다.", headers=headers) from None


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
    headers = {"X-Request-ID": request_id}
    try:
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
            generate=mock_generate if _mock_enabled(mock) else None,
        )
    except HTTPException:
        raise
    except repository.DecisionRetryConflictError:
        raise HTTPException(
            409, "재시도할 실패 상태·저장 자료를 확인하세요.", headers=headers
        ) from None
    except (RuntimeError, TimeoutError):
        raise HTTPException(502, "최종판단 서비스에 실패했습니다.", headers=headers) from None
    except Exception:
        raise HTTPException(
            500, "최종판단 검증 또는 저장에 실패했습니다.", headers=headers
        ) from None
