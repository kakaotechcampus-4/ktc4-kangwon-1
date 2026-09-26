"""HTTP 재시도·응답 종료 검증을 한 경계에 둡니다."""

import json
from typing import Any

import openai
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

from .config import LLMSettings


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


async def _complete(
    messages: list[Any], settings: LLMSettings, *, tools: list[Any] | None = None
) -> ChatCompletionMessage:
    settings.require_credentials()
    options: dict[str, Any] = {}
    if settings.max_tokens is not None:
        options["max_completion_tokens"] = settings.max_tokens
    if settings.reasoning_effort is not None:
        options["reasoning_effort"] = settings.reasoning_effort
    if tools is None:
        options["response_format"] = {"type": "json_object"}
    else:
        options.update(tools=tools, tool_choice="required", parallel_tool_calls=False)
    try:
        async with openai.AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
            max_retries=1,
        ) as client:
            response = await client.chat.completions.create(
                model=settings.model or "", messages=messages, **options
            )
    except openai.APIStatusError as exc:
        raise LLMHTTPError(exc.status_code, exc.body) from None
    except openai.APITimeoutError:
        raise LLMResponseError("LLM_TIMEOUT") from None
    except openai.APIConnectionError:
        raise LLMResponseError("LLM_CONNECTION_ERROR") from None
    except (openai.APIError, ValueError, TypeError):
        raise LLMResponseError("LLM_REQUEST_ERROR") from None
    if (
        not isinstance(response, ChatCompletion)
        or not isinstance(response.choices, list)
        or not response.choices
    ):
        raise LLMResponseError("LLM_INVALID_RESPONSE")
    choice = response.choices[0]
    if not isinstance(choice, Choice) or not isinstance(choice.message, ChatCompletionMessage):
        raise LLMResponseError("LLM_INVALID_RESPONSE")
    finish = choice.finish_reason
    safe_finish = (
        finish
        if finish in {"stop", "length", "tool_calls", "content_filter", "function_call"}
        else "unknown"
    )
    if choice.message.refusal or finish == "content_filter":
        raise LLMResponseError("LLM_REFUSED", finish_reason=safe_finish)
    if finish == "length":
        raise LLMResponseError("LLM_OUTPUT_LIMIT", finish_reason=safe_finish)
    if finish != ("stop" if tools is None else "tool_calls"):
        raise LLMResponseError("LLM_INCOMPLETE", finish_reason=safe_finish)
    return choice.message


async def complete_json(
    system_prompt: str, input_json: str, settings: LLMSettings
) -> dict[str, Any]:
    message = await _complete(
        [
            {"role": "system", "content": system_prompt + "\n반드시 JSON 객체만 출력하세요."},
            {"role": "user", "content": input_json},
        ],
        settings,
    )
    try:
        # 표준 JSON에 없는 NaN·Infinity도 모델의 잘못된 응답입니다.
        def invalid_constant(_value: str) -> None:
            raise ValueError

        result = json.loads(message.content or "", parse_constant=invalid_constant)
        if not isinstance(result, dict):
            raise ValueError
    except (ValueError, TypeError):
        raise LLMResponseError("LLM_INVALID_JSON") from None
    return result


async def complete_tools(
    messages: list[Any], definitions: list[Any], settings: LLMSettings
) -> ChatCompletionMessage:
    return await _complete(messages, settings, tools=definitions)
