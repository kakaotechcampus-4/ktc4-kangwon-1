"""배치별 설명을 생성하되 계산한 점수와 업종 계약을 복원합니다."""

import json
from typing import Any

from app.llm import client
from app.llm.config import LLMSettings


async def analyze_batches(
    agent_input: dict[str, Any], settings: LLMSettings | None = None
) -> dict[str, Any]:
    from .agent import BATCH_SIZE, SYSTEM_PROMPT, validate_llm_result

    settings = settings or LLMSettings.from_env("BUSINESS_LIFECYCLE")
    industries = agent_input["industries"]
    scores: list[dict[str, Any]] = []
    for start in range(0, len(industries), BATCH_SIZE):
        batch = {
            "scope": agent_input["scope"],
            "scoring_method": agent_input["scoring_method"],
            "industries": industries[start : start + BATCH_SIZE],
        }
        result = await client.complete_json(
            SYSTEM_PROMPT, json.dumps(batch, ensure_ascii=False), settings
        )
        validate_llm_result(batch, result)
        scores.extend(result["industry_scores"])
    result = {
        "summary": (
            f"최근 {agent_input['scope']['period']['quarter_count']}개 분기의 개폐업 데이터를 "
            f"기반으로 {len(scores)}개 업종을 분석했습니다."
        ),
        "industry_scores": scores,
    }
    validate_llm_result(agent_input, result)
    return result
