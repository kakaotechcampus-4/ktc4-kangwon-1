"""최종판단 스키마를 검증하며 모델 실패를 대체하지 않습니다."""

import json
from typing import Any

from pydantic import ValidationError

from app.llm import client
from app.llm.config import LLMSettings
from app.schemas import (
    EVALUATOR_IDS,
    ConsultPlan,
    DecisionContent,
    EvaluationLogEntry,
    MapLookupPlan,
    QuestionPlan,
    SupplementPlan,
)


def split_evaluation_log(produced, evaluation: dict) -> tuple[Any, list[EvaluationLogEntry]]:
    """공통 판단 검증 전에 로그를 분리하고 실제 지적과 일대일로 맞춥니다."""
    keys = {
        (item["evaluator"], comment["index"])
        for item in evaluation["evaluations"]
        for comment in item["comments"]
    }
    raw = None
    if isinstance(produced, dict):
        produced = dict(produced)
        raw = produced.pop("evaluation_log", None)
    entries: dict[tuple, EvaluationLogEntry] = {}
    for item in raw if isinstance(raw, list) else []:
        try:
            entry = EvaluationLogEntry.model_validate(item)
        except ValidationError:
            continue
        key = (entry.evaluator, entry.index)
        if key in keys and entry.decision != "unreviewed":
            entries.setdefault(key, entry)
    return produced, [
        entries.get((role, index))
        or EvaluationLogEntry(
            evaluator=role,
            index=index,
            decision="unreviewed",
            reason="판정관이 이 지적을 검토하지 않았습니다.",
        )
        for role, index in sorted(keys, key=lambda key: (EVALUATOR_IDS.index(key[0]), key[1]))
    ]


class InvalidDecisionCategory(ValueError):
    """검증 전 출력은 교정 입력으로만 보관하고 공개 진단에는 넣지 않습니다."""

    def __init__(self, payload: dict, field: str):
        super().__init__("업종 코드 또는 명칭이 공통 업종표와 일치하지 않습니다.")
        self.payload = payload
        self.field = field


def validate_content(payload) -> DecisionContent:
    """공통 계약은 유지하면서 모델의 업종 오류만 교정 단계로 전달합니다."""
    try:
        return DecisionContent.model_validate(payload)
    except ValidationError as exc:
        errors = exc.errors()
        if isinstance(payload, dict) and all(
            len(e["loc"]) == 3
            and e["loc"][0] in {"recommendations", "not_recommended"}
            and isinstance(e["loc"][1], int)
            and e["loc"][2] == "category"
            and e["type"] == "value_error"
            for e in errors
        ):
            field = ".".join(str(part) for part in errors[0]["loc"])
            raise InvalidDecisionCategory(payload, field) from None
        raise


async def generate_decision(
    system_prompt: str, input_json: str, settings: LLMSettings | None = None
) -> DecisionContent | SupplementPlan | QuestionPlan | MapLookupPlan | ConsultPlan | dict:
    payload = await client.complete_json(
        system_prompt, input_json, settings or LLMSettings.from_env("DECISION")
    )
    if "evaluation" in json.loads(input_json):
        # 평가 로그는 evaluate에서 분리한 뒤 기존 판단 검증과 교정 경로를 통과시킵니다.
        return payload
    schema = (
        ConsultPlan
        if isinstance(payload, dict) and payload.get("action") == "ask_specialists"
        else SupplementPlan
        if isinstance(payload, dict) and payload.get("action") == "supplement"
        else QuestionPlan
        if isinstance(payload, dict) and payload.get("action") == "ask_user"
        else MapLookupPlan
        if isinstance(payload, dict) and payload.get("action") == "map_lookup"
        else DecisionContent
    )
    if schema is ConsultPlan and isinstance(payload.get("queries"), list):
        # 같은 전문가에게 겹친 질문은 첫 질문만 남깁니다. 허용 대상 확인은 판정 에이전트가 합니다.
        seen: set = set()
        kept = []
        for query in payload["queries"]:
            agent_id = query.get("agent_id") if isinstance(query, dict) else None
            if agent_id is None or agent_id not in seen:
                seen.add(agent_id)
                kept.append(query)
        payload["queries"] = kept
    try:
        if schema is DecisionContent:
            return validate_content(payload)
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
