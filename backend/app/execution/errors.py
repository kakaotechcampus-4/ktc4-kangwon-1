"""교정 진단을 예외 계약 또는 요청 범위에 명시적으로 보관합니다."""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from functools import wraps
from typing import Any


class FailureDiagnostics:
    """코드가 정제한 진단 목록을 가지는 예외의 명시적인 계약입니다."""

    failures: list[dict[str, Any]]


class DecisionExecutionError(FailureDiagnostics, RuntimeError):
    def __init__(self, error: Exception, failures: list[dict[str, Any]]):
        super().__init__("최종판단 교정 실행에 실패했습니다.")
        self.error = error
        self.failures = deepcopy(failures)


class DecisionTimeoutError(DecisionExecutionError, TimeoutError):
    """판정관 직접 호출의 기존 TimeoutError 계약을 유지합니다."""

    def __init__(self, error: Exception, failures: list[dict[str, Any]]):
        super().__init__(error, failures)
        self.args = error.args


class DecisionValidationExecutionError(DecisionExecutionError, ValueError):
    """판정관 직접 호출의 기존 ValueError 계약을 유지합니다."""

    def __init__(self, error: Exception, failures: list[dict[str, Any]]):
        super().__init__(error, failures)
        self.args = error.args


@dataclass
class _FailureScope:
    error: BaseException | None = None
    failures: list[dict[str, Any]] | None = None


_FAILURES: ContextVar[_FailureScope | None] = ContextVar("decision_failures", default=None)


def capture_decision_failures[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """서비스가 실패를 저장할 때까지 진단을 보관하고 원래 예외를 전파합니다."""

    @wraps(fn)
    async def scoped(*args: P.args, **kwargs: P.kwargs) -> R:
        token = _FAILURES.set(_FailureScope())
        try:
            return await fn(*args, **kwargs)
        except DecisionExecutionError as error:
            raise error.error from None
        finally:
            _FAILURES.reset(token)

    return scoped


def remember_failure(error: BaseException, failures: list[dict[str, Any]]) -> None:
    scope = _FAILURES.get()
    if scope is not None:
        scope.error = error
        scope.failures = deepcopy(failures)


def failure_diagnostics(error: BaseException) -> list[dict[str, Any]] | None:
    if isinstance(error, FailureDiagnostics):
        return deepcopy(error.failures)
    scope = _FAILURES.get()
    if scope is None:
        return None
    # asyncio.timeout이 취소를 TimeoutError로 바꾸어도 같은 원인의 진단을 보존합니다.
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if current is scope.error:
            return deepcopy(scope.failures)
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None
