"""배치별 설명을 생성하되 계산한 점수와 업종 계약을 복원합니다."""

import asyncio
import json
from pathlib import Path
from typing import Any

from app.industries.catalog import INDUSTRIES
from app.llm import client
from app.llm.config import LLMSettings

BATCH_SIZE = 10
PROMPT_PATH = Path(__file__).with_name("prompt.md")
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")


class BusinessLifecycleAgentError(RuntimeError):
    """Business Lifecycle Agent 실행 오류."""


async def analyze_batches(
    agent_input: dict[str, Any], settings: LLMSettings | None = None
) -> dict[str, Any]:
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


def validate_llm_result(
    agent_input: dict[str, Any],
    llm_result: dict[str, Any],
) -> None:
    """
    LLM이 입력으로 받은 모든 업종을
    정확히 반환했는지 확인.
    """

    input_industries = agent_input["industries"]

    output_industries = llm_result.get(
        "industry_scores",
        [],
    )

    if not isinstance(input_industries, list) or not all(
        isinstance(industry, dict)
        and isinstance(industry.get("industry_id"), str)
        and industry["industry_id"] in INDUSTRIES
        for industry in input_industries
    ):
        raise BusinessLifecycleAgentError("계산 업종 목록이 올바르지 않습니다.")
    if not isinstance(output_industries, list) or not all(
        isinstance(industry, dict)
        and isinstance(industry.get("industry_id"), str)
        and industry["industry_id"] in INDUSTRIES
        for industry in output_industries
    ):
        raise BusinessLifecycleAgentError("LLM 업종 결과가 올바르지 않습니다.")

    input_ids = [industry["industry_id"] for industry in input_industries]
    output_ids = [industry.get("industry_id") for industry in output_industries]

    if (
        len(input_ids) != len(set(input_ids))
        or len(output_ids) != len(set(output_ids))
        or set(input_ids) != set(output_ids)
    ):
        missing = set(input_ids) - set(output_ids)
        extra = set(output_ids) - set(input_ids)

        raise BusinessLifecycleAgentError(
            "LLM 업종 결과가 입력과 일치하지 않습니다. "
            f"누락={sorted(missing)}, "
            f"추가={sorted(extra)}"
        )

    calculated = {industry["industry_id"]: industry for industry in input_industries}
    for industry in output_industries:
        source = calculated[industry["industry_id"]]
        for field in ("industry_name", "lifecycle_score", "confidence"):
            industry[field] = source[field]
        for field in ("metrics", "data_status", "data_complete"):
            if field in source:
                industry[field] = source[field]


def run_llm_analysis(
    agent_input: dict[str, Any], settings: LLMSettings | None = None
) -> dict[str, Any]:
    """동기 파이프라인의 작업 스레드에서만 비동기 모델 호출로 연결합니다."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(analyze_batches(agent_input, settings))
    raise RuntimeError("실행 중인 이벤트 루프에서는 analyze_batches를 await해 주세요.")
