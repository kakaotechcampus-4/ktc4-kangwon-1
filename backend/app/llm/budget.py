"""요청별 모델 예산을 병렬 작업과 질문 재개에서 공유합니다."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field

from app.logging import log_exception

logger = logging.getLogger(__name__)


MAX_CALLS = 24
EVALUATED_MAX_CALLS = 64
# 최종판단·교정 몫입니다. 전문가 호출은 이 몫을 쓰지 못합니다.
FINAL_RESERVE = 2


class BudgetExceeded(RuntimeError):
    code = "LLM_BUDGET_EXHAUSTED"

    def __init__(self):
        super().__init__("요청의 모델 호출 예산을 모두 사용했습니다.")


class BudgetStorageError(RuntimeError):
    """예산 저장 실패를 모델 응답 실패와 구분합니다."""

    code = "STORAGE_FAILED"


@dataclass
class LLMBudget:
    limit: int = MAX_CALLS
    used: int = 0
    calls: list[dict] = field(default_factory=list)
    on_change: Callable[[dict], Awaitable[None]] | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def __post_init__(self):
        if type(self.used) is not int or not 0 <= self.used <= self.limit <= EVALUATED_MAX_CALLS:
            raise ValueError("모델 호출 예산이 올바르지 않습니다.")

    @property
    def open_calls(self) -> int:
        """전문가가 쓸 수 있는 남은 호출 수입니다."""
        return max(0, self.limit - FINAL_RESERVE - self.used)

    def snapshot(self) -> dict:
        return {"used": self.used, "calls": deepcopy(self.calls)}

    async def _save(self) -> None:
        if self.on_change is not None:
            try:
                await self.on_change(self.snapshot())
            except Exception as exc:
                log_exception(logger, "모델 예산 저장 실패", exc)
                raise BudgetStorageError("모델 호출 이력을 저장하지 못했습니다.") from exc

    async def reserve(self, role: str, *, final: bool, input_chars: int | None = None) -> int:
        async with self._lock:
            if self.used >= self.limit - (0 if final else FINAL_RESERVE):
                raise BudgetExceeded()
            self.used += 1
            self.calls.append(
                {
                    "attempt": self.used,
                    "role": role,
                    "status": "started",
                    "input_tokens": None,
                    "output_tokens": None,
                    "input_chars": input_chars,
                }
            )
            await self._save()
            return self.used

    async def finish(self, attempt: int, *, status: str, elapsed_ms: int, usage=None) -> None:
        async with self._lock:
            record = next(row for row in self.calls if row["attempt"] == attempt)
            record.update(status=status, elapsed_ms=elapsed_ms)
            if usage is not None:
                record.update(
                    input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens
                )
            await self._save()


_SCOPE: ContextVar[tuple[LLMBudget | None, str, bool]] = ContextVar(
    "llm_budget", default=(None, "decision", True)
)


def current_scope() -> tuple[LLMBudget | None, str, bool]:
    return _SCOPE.get()


@contextmanager
def llm_scope(budget: LLMBudget | None, role: str, *, final: bool = False) -> Iterator[None]:
    token = _SCOPE.set((budget, role, final))
    try:
        yield
    finally:
        _SCOPE.reset(token)
