"""사용자 요청을 받아 분석 흐름을 실행하는 v1 API입니다."""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.address import GeocodeError
from app.mocks import mock_agents, mock_generate, mock_site
from app.orchestrator import run_analysis
from app.schemas import DecisionResult

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
    mock: bool = Query(
        default=False,
        description="외부 API·모델 호출 없이 고정 응답을 돌려줍니다. 화면 연동용입니다.",
    ),
) -> DecisionResult:
    """주소 → 좌표 → 분석 에이전트 병렬 실행 → 중재까지 한 번에 실행합니다.

    `mock=true`이거나 `MOCK_MODE` 환경변수가 켜져 있으면 외부 호출 없이
    같은 형태의 고정 응답을 돌려줍니다. 키가 없어도 화면을 붙일 수 있습니다.
    """
    if _mock_enabled(mock):
        return await run_analysis(
            body.address,
            site=mock_site(body.address),
            agents=mock_agents(),
            generate=mock_generate,
        )

    try:
        return await run_analysis(body.address)
    except GeocodeError as exc:
        raise HTTPException(
            status_code=400, detail=f"주소를 찾지 못했습니다: {exc.message}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
