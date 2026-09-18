"""백엔드 서버의 진입점입니다."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.config import load_environment
from app.db.connection import initialize
from app.services.settings import ExecutionSettings

DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def allowed_origins() -> list[str]:
    """프론트엔드 주소를 환경변수로 받습니다.

    배포 주소가 생기면 `CORS_ALLOW_ORIGINS`에 쉼표로 이어 붙입니다.
    """
    raw = os.getenv("CORS_ALLOW_ORIGINS", DEFAULT_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await asyncio.to_thread(initialize, app.state.execution_settings.db_path)
    yield


def create_app(*, settings: ExecutionSettings | None = None, load_env: bool = True) -> FastAPI:
    """uvicorn --factory 진입점. 환경 → 실행 설정·CORS → lifespan DB 순서입니다."""
    if load_env:
        load_environment()
    app = FastAPI(
        lifespan=lifespan,
        title="채움 API",
        version="0.1.0",
        description="공실 주소를 받아 업종 추천 리포트를 돌려주는 API입니다.",
    )
    app.state.execution_settings = settings or ExecutionSettings.from_env()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.include_router(v1_router)

    @app.get("/health", summary="상태 확인")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
