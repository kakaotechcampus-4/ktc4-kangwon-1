"""오케스트레이터는 한 번에 하나의 도구 호출만 허용합니다."""

from typing import Any

from openai.types.chat import ChatCompletionMessage

from app.llm import client
from app.llm.config import LLMSettings


async def generate_action(
    messages: list[Any], definitions: list[Any], settings: LLMSettings | None = None
) -> ChatCompletionMessage:
    message = await client.complete_tools(
        messages, definitions, settings or LLMSettings.from_env("ORCHESTRATION")
    )
    if not message.tool_calls or len(message.tool_calls) != 1:
        raise RuntimeError("한 번에 하나의 도구 호출이 필요합니다.")
    return message
