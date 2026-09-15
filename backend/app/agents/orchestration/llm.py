"""엘리스 호환 API에서 다음 도구 호출을 받습니다."""

import math
import os
from typing import Any

from openai import APIError, APIStatusError, AsyncOpenAI
from openai.types.chat import ChatCompletionMessage


async def generate_action(messages: list[Any], definitions: list[Any]) -> ChatCompletionMessage:
    """도구 호출 응답만 허용하며 모델 오류를 목업으로 대체하지 않습니다."""
    values = {}
    for key in ("ELICE_MODEL", "ELICE_API_KEY", "ELICE_BASE_URL"):
        values[key] = os.getenv(key, "").strip()
        if not values[key]:
            raise ValueError(f"{key}를 설정해 주세요.")
    try:
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", "8192"))
        timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
    except ValueError as exc:
        raise ValueError("응답 길이와 대기 시간은 양수로 설정해 주세요.") from exc
    if max_tokens <= 0 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("응답 길이와 대기 시간은 양수로 설정해 주세요.")
    try:
        async with AsyncOpenAI(
            api_key=values["ELICE_API_KEY"], base_url=values["ELICE_BASE_URL"],
            timeout=timeout, max_retries=1,
        ) as client:
            response = await client.chat.completions.create(
                model=values["ELICE_MODEL"], messages=messages, tools=definitions,
                tool_choice="required", parallel_tool_calls=False,
                reasoning_effort="none",
                max_completion_tokens=max_tokens,
            )
    except APIStatusError as exc:
        raise RuntimeError(
            f"오케스트레이터 모델 요청이 HTTP {exc.status_code}로 거절되었습니다. "
            "모델의 도구 호출 지원과 설정을 확인해 주세요."
        ) from exc
    except APIError as exc:
        raise RuntimeError("오케스트레이터 모델 연결에 실패했습니다.") from exc
    if not response.choices:
        raise RuntimeError("모델이 도구 호출을 반환하지 않았습니다.")
    choice = response.choices[0]
    if choice.finish_reason != "tool_calls" or choice.message.refusal:
        raise RuntimeError("모델이 도구 호출을 완료하지 못했습니다. 거절·길이 제한을 확인하세요.")
    if not choice.message.tool_calls or len(choice.message.tool_calls) != 1:
        raise RuntimeError("한 번에 하나의 도구 호출이 필요합니다.")
    return choice.message
