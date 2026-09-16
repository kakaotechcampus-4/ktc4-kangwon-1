"""백엔드 서버의 진입점입니다."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router

DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def allowed_origins() -> list[str]:
    """프론트엔드 주소를 환경변수로 받습니다.

    배포 주소가 생기면 `CORS_ALLOW_ORIGINS`에 쉼표로 이어 붙입니다.
    """
    raw = os.getenv("CORS_ALLOW_ORIGINS", DEFAULT_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(
    title="채움 API",
    version="0.1.0",
    description="공실 주소를 받아 업종 추천 리포트를 돌려주는 API입니다.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)


@app.get("/health", summary="상태 확인")
async def health() -> dict[str, str]:
    return {"status": "ok"}
