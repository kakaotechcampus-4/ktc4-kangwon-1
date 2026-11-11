from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from functools import wraps
from pathlib import Path
from typing import Any, Protocol

from app.application.ports.llm_settings import LLMSettings
from app.application.ports.slot import Slot


class LLMResponseError(RuntimeError):
    """원문 대신 코드와 호출자가 정제한 진단 정보만 보존합니다."""

    MESSAGES = {
        "LLM_TIMEOUT": "모델 요청 시간이 초과됐습니다.",
        "LLM_CONNECTION_ERROR": "모델 서버에 연결하지 못했습니다.",
        "LLM_REQUEST_ERROR": "모델 요청 처리에 실패했습니다.",
        "LLM_INVALID_RESPONSE": "모델이 유효한 응답을 반환하지 않았습니다.",
        "LLM_OUTPUT_LIMIT": "모델 응답이 길이 제한으로 중단됐습니다.",
        "LLM_REFUSED": "모델 응답이 거절되거나 필터링됐습니다.",
        "LLM_INCOMPLETE": "모델이 예상한 종료 형식으로 응답을 완료하지 못했습니다.",
        "LLM_INVALID_JSON": "모델 응답 형식이 올바른 JSON 객체가 아닙니다.",
        "LLM_SCHEMA_INVALID": "모델 응답 형식이 올바르지 않습니다. 필드 검증에 실패했습니다.",
    }

    def __init__(self, code: str, **diagnostics: Any):
        self.code = code
        self.diagnostics = diagnostics
        message = self.MESSAGES[code]
        if code == "LLM_SCHEMA_INVALID":
            message += " 확인 항목: " + ", ".join(diagnostics.get("fields", []))
        super().__init__(message)


class LLMHTTPError(RuntimeError):
    """서버 원문 대신 허용된 진단 항목만 전달합니다."""

    def __init__(self, status: int, body: Any):
        super().__init__(f"모델 요청이 HTTP {status}로 거절되었습니다.")
        error = body.get("error", body) if isinstance(body, dict) else {}
        error = error if isinstance(error, dict) else {}
        codes = {
            "unsupported_value",
            "unsupported_parameter",
            "invalid_value",
            "invalid_parameter",
            "invalid_request_error",
            "missing_required_parameter",
            "model_not_found",
            "invalid_api_key",
            "insufficient_quota",
            "rate_limit_exceeded",
            "context_length_exceeded",
            "permission_denied",
        }
        parameters = {
            "reasoning_effort",
            "model",
            "messages",
            "tools",
            "tool_choice",
            "parallel_tool_calls",
            "response_format",
            "max_tokens",
            "max_completion_tokens",
            "temperature",
            "top_p",
        }
        code, parameter = error.get("code"), error.get("param")
        self.diagnostics = {
            "http_status": status,
            "provider_code": code if isinstance(code, str) and code in codes else "unknown",
            "parameter": parameter
            if isinstance(parameter, str) and parameter in parameters
            else "unknown",
        }


_TRANSPORT_RETRY_STATUSES = frozenset({429, 502, 503, 504})
_TRANSIENT_STATUSES = _TRANSPORT_RETRY_STATUSES | {500}
_TRANSIENT_CODES = frozenset({"LLM_TIMEOUT", "LLM_CONNECTION_ERROR"})


def _credit_exhausted(exc: LLMHTTPError) -> bool:
    return exc.diagnostics.get("provider_code") == "insufficient_quota"


def is_transport_retried(exc: BaseException) -> bool:
    if isinstance(exc, LLMResponseError):
        return exc.code == "LLM_CONNECTION_ERROR"
    if isinstance(exc, LLMHTTPError):
        return exc.diagnostics.get(
            "http_status"
        ) in _TRANSPORT_RETRY_STATUSES and not _credit_exhausted(exc)
    return False


def is_transient(exc: BaseException) -> bool:
    if isinstance(exc, LLMResponseError):
        return exc.code in _TRANSIENT_CODES
    if isinstance(exc, LLMHTTPError):
        return exc.diagnostics.get("http_status") in _TRANSIENT_STATUSES and not _credit_exhausted(
            exc
        )
    return False


class Recorder(Protocol):
    async def record(
        self,
        role: str,
        messages: Any,
        value: Any,
        receipt: dict[str, Any],
        elapsed_ms: int,
        error: BaseException | None = None,
    ) -> None: ...


class LanguageModel(Protocol):
    async def complete_json(
        self,
        system_prompt: str,
        input_json: str,
        settings: LLMSettings,
        *,
        receipt: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
    async def complete_tools(
        self,
        messages: list[Any],
        definitions: list[Any],
        settings: LLMSettings,
        *,
        receipt: dict[str, Any] | None = None,
    ) -> Any: ...
    def recording(self, request_id: str, path: Path | None = None) -> Recorder: ...
    def session(self) -> AbstractAsyncContextManager[Any]: ...


llm: Slot[LanguageModel] = Slot()


def with_llm_session[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(fn)
    async def scoped(*args: P.args, **kwargs: P.kwargs) -> R:
        async with llm().session():
            return await fn(*args, **kwargs)

    return scoped
