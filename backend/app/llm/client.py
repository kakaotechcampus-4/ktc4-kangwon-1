"""HTTP 재시도·응답 종료 검증을 한 경계에 둡니다."""

import json
from typing import Any

import openai
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

from .config import LLMSettings


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
        raise RuntimeError(f"모델 요청이 HTTP {exc.status_code}로 거절되었습니다.") from None
    except (openai.APIError, ValueError, TypeError):
        raise RuntimeError(
            "모델 요청에 실패했습니다. 연결 상태와 모델 설정을 확인해 주세요."
        ) from None
    if (
        not isinstance(response, ChatCompletion)
        or not isinstance(response.choices, list)
        or not response.choices
    ):
        raise RuntimeError("모델이 응답을 반환하지 않았습니다.")
    choice = response.choices[0]
    if (
        not isinstance(choice, Choice)
        or not isinstance(choice.message, ChatCompletionMessage)
        or choice.finish_reason != ("stop" if tools is None else "tool_calls")
        or choice.message.refusal
    ):
        raise RuntimeError("모델이 응답을 완료하지 못했습니다. 거절·길이 제한을 확인해 주세요.")
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
        raise RuntimeError("모델 응답 형식이 올바른 JSON 객체가 아닙니다.") from None
    return result


async def complete_tools(
    messages: list[Any], definitions: list[Any], settings: LLMSettings
) -> ChatCompletionMessage:
    return await _complete(messages, settings, tools=definitions)
