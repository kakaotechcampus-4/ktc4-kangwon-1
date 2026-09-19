"""사용자 요청을 받아 분석 흐름을 실행하는 v1 API입니다."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.address import GeocodeError
from app.db import repository
from app.mocks import mock_action, mock_agents, mock_generate, mock_resolve
from app.schemas import DecisionResult
from app.services.analysis import execute_analysis

router = APIRouter(prefix="/api/v1", tags=["analysis"])


class AnalysisRequest(BaseModel):
    """분석 요청 본문입니다."""

    address: str = Field(
        min_length=1,
        max_length=200,
        description="분석할 공실의 주소. 상세주소가 붙어 있어도 됩니다.",
        examples=["서울특별시 노원구 한글비석로 242 삼부프라자 1층"],
    )


def _mock_enabled(requested: bool) -> bool:
    return requested or os.getenv("MOCK_MODE", "").strip().lower() in {"1", "true", "yes"}


@router.get("/health", summary="상태 확인")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/analyses",
    response_model=DecisionResult,
    response_model_exclude_none=True,
    summary="주소 하나로 업종 추천 리포트를 만듭니다",
)
async def create_analysis(
    body: AnalysisRequest,
    request: Request,
    response: Response,
    mock: bool = Query(
        default=False,
        description="외부 API·모델 호출 없이 고정 응답을 돌려줍니다. 화면 연동용입니다.",
    ),
) -> DecisionResult:
    """주소 → 좌표 → 분석 에이전트 병렬 실행 → 중재까지 한 번에 실행합니다.

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
            return await execute_analysis(
                body.address,
                settings=request.app.state.execution_settings,
                request_id=request_id,
                resolve=mock_resolve,
                agents=mock_agents(),
                generate=mock_generate,
                generate_action=mock_action,
            )
        return await execute_analysis(
            body.address, settings=request.app.state.execution_settings, request_id=request_id
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
            # 과거 업종명·스키마는 저장 당시 값 그대로 반환합니다.
            for name in ("site", "result", "error"):
                value = row.pop(f"{name}_json")
                row[name] = json.loads(value) if value is not None else None
            return row
    except Exception as exc:
        raise HTTPException(status_code=500, detail="저장된 분석 조회에 실패했습니다.") from exc
    raise HTTPException(status_code=404, detail="분석 요청을 찾을 수 없습니다.")
