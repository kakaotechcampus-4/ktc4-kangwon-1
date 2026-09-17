"""최종판단 스키마를 검증하며 모델 실패를 대체하지 않습니다."""

from pydantic import ValidationError

from app.llm import client
from app.llm.config import LLMSettings
from app.schemas import DecisionContent


async def generate_decision(
    system_prompt: str, input_json: str, settings: LLMSettings | None = None
) -> DecisionContent:
    payload = await client.complete_json(
        system_prompt, input_json, settings or LLMSettings.from_env("DECISION")
    )
    try:
        return DecisionContent.model_validate(payload)
    except ValidationError as exc:
        # 알 수 없는 추가 키는 모델이 만든 문자열이므로 공개 오류에 싣지 않습니다.
        fields = list(
            dict.fromkeys(
                str(error["loc"][0])
                for error in exc.errors()
                if error["loc"] and error["loc"][0] in DecisionContent.model_fields
            )
        )
        raise RuntimeError(
            "모델 응답 형식이 올바르지 않습니다. 확인 항목: " + ", ".join(fields[:3])
        ) from None
