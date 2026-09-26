"""최종판단 스키마를 검증하며 모델 실패를 대체하지 않습니다."""

from pydantic import ValidationError

from app.llm import client
from app.llm.config import LLMSettings
from app.schemas import DecisionContent, SupplementPlan


async def generate_decision(
    system_prompt: str, input_json: str, settings: LLMSettings | None = None
) -> DecisionContent | SupplementPlan:
    payload = await client.complete_json(
        system_prompt, input_json, settings or LLMSettings.from_env("DECISION")
    )
    schema = (
        SupplementPlan
        if isinstance(payload, dict) and payload.get("action") == "supplement"
        else DecisionContent
    )
    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        # 알 수 없는 추가 키는 모델이 만든 문자열이므로 공개 오류에 싣지 않습니다.
        fields = list(
            dict.fromkeys(
                str(error["loc"][0])
                for error in exc.errors()
                if error["loc"] and error["loc"][0] in schema.model_fields
            )
        )
        definition = schema.model_json_schema()
        allowed_fields = set(schema.model_fields)
        for nested in definition.get("$defs", {}).values():
            allowed_fields.update(nested.get("properties", {}))
        allowed_types = {
            "missing",
            "extra_forbidden",
            "string_type",
            "int_type",
            "float_type",
            "list_type",
            "dict_type",
            "literal_error",
            "value_error",
            "too_long",
            "too_short",
            "greater_than_equal",
            "less_than_equal",
            "string_too_short",
            "model_type",
        }
        errors = []
        for error in exc.errors()[:8]:
            path = [
                str(part) if isinstance(part, int) or part in allowed_fields else "unknown"
                for part in error["loc"]
            ]
            errors.append(
                {
                    "path": ".".join(path) or "root",
                    "type": error["type"] if error["type"] in allowed_types else "validation_error",
                }
            )
        raise client.LLMResponseError(
            "LLM_SCHEMA_INVALID",
            fields=fields[:8],
            schema=schema.__name__,
            validation_errors=errors,
            error_count=exc.error_count(),
        ) from None
