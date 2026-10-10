"""한 분석 실행 안에서 같은 설정의 모델 연결만 재사용합니다."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from contextvars import ContextVar
from functools import wraps

import openai

from .config import LLMSettings


class LLMClientSession:
    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stack = AsyncExitStack()
        self._clients: dict[tuple[LLMSettings, int], openai.AsyncOpenAI] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    def validate(self) -> None:
        if self._closed or asyncio.get_running_loop() is not self._loop:
            raise RuntimeError("모델 연결은 생성된 실행과 이벤트 루프 안에서만 사용할 수 있습니다.")

    async def get(self, settings: LLMSettings, max_retries: int) -> openai.AsyncOpenAI:
        self.validate()
        key = settings, max_retries
        async with self._lock:
            self.validate()
            if key not in self._clients:
                self._clients[key] = await self._stack.enter_async_context(
                    _new_client(settings, max_retries)
                )
            return self._clients[key]

    async def close(self) -> None:
        self._closed = True
        closing = asyncio.create_task(self._stack.aclose())
        cancelled = False
        while not closing.done():
            try:
                await asyncio.shield(closing)
            except asyncio.CancelledError:
                cancelled = True
        closing.result()
        self._clients.clear()
        if cancelled:
            raise asyncio.CancelledError


_SESSION: ContextVar[LLMClientSession | None] = ContextVar("llm_client_session", default=None)


def _new_client(settings: LLMSettings, max_retries: int) -> openai.AsyncOpenAI:
    return openai.AsyncOpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=settings.timeout_seconds,
        max_retries=max_retries,
    )


@asynccontextmanager
async def acquire_client(settings: LLMSettings, *, max_retries: int):
    session = _SESSION.get()
    if session is not None:
        yield await session.get(settings, max_retries)
    else:
        # 직접 함수 호출은 기존처럼 해당 호출이 연결을 닫습니다.
        async with _new_client(settings, max_retries) as client:
            yield client


@asynccontextmanager
async def client_session_scope():
    current = _SESSION.get()
    if current is not None:
        current.validate()
        yield current
        return
    session = LLMClientSession()
    token = _SESSION.set(session)
    try:
        yield session
    finally:
        _SESSION.reset(token)
        await session.close()


def with_client_session[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(fn)
    async def scoped(*args: P.args, **kwargs: P.kwargs) -> R:
        async with client_session_scope():
            return await fn(*args, **kwargs)

    return scoped
