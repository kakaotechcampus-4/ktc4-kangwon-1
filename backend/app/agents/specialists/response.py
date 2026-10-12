"""도구 응답 해석과 브리핑 내용의 부분 형식 검증입니다."""

import json
from dataclasses import dataclass

from openai.types.chat import ChatCompletionMessage
from pydantic import Field, ValidationError

from app.evidence import FINDING_WARNING_PREFIX
from app.schemas import Finding, Schema, Text


class BriefContent(Schema):
    headline: str = Field(min_length=1, max_length=200)
    findings: list[Finding] = Field(max_length=8)
    limitations: list[Text] = Field(default_factory=list)


@dataclass(frozen=True)
class ToolResponse:
    message: ChatCompletionMessage
    name: str
    arguments: dict
    call_id: str


def parse_tool_response(produced) -> ToolResponse:
    message = ChatCompletionMessage.model_validate(produced)
    if not message.tool_calls or len(message.tool_calls) != 1:
        raise ValueError("도구는 한 번에 하나만 선택합니다.")
    call = message.tool_calls[0]
    if call.type != "function":
        raise ValueError("지원하지 않는 도구 종류입니다.")
    arguments = json.loads(call.function.arguments)
    if not isinstance(arguments, dict):
        raise ValueError("도구 인자는 객체여야 합니다.")
    return ToolResponse(message, call.function.name, arguments, call.id)


def parse_finish(arguments: dict) -> BriefContent:
    """형식이 틀린 주장 하나만 제외하고 기존 상한과 경고를 유지합니다."""
    raw = arguments.get("findings")
    kept, dropped = [], []
    for i, item in enumerate(raw if isinstance(raw, list) else []):
        try:
            kept.append(Finding.model_validate(item))
        except ValidationError:
            dropped.append(f"{FINDING_WARNING_PREFIX}: {i + 1}번 형식 오류")
    content = BriefContent.model_validate({**arguments, "findings": kept[:8]})
    content.limitations.extend(dropped)
    return content
