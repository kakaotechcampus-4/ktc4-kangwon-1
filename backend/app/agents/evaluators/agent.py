"""평가 의견을 원자료 경로로 검증하며 일반 모델 실패를 격리합니다."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from importlib.resources import files

from pydantic import ValidationError

from app.agents.decision.context import build_context
from app.evidence import index_paths, valid_map_path
from app.llm.budget import BudgetStorageError, current_scope, llm_scope
from app.llm.client import complete_json
from app.llm.config import LLMSettings
from app.logging import log_exception
from app.schemas import (
    DecisionRequest,
    DecisionResult,
    Evaluation,
    EvaluationComment,
    EvaluationRequest,
    EvaluatorId,
)

logger = logging.getLogger(__name__)


GenerateEvaluation = Callable[[str, str], Awaitable[dict]]


def decision_evaluation(draft: DecisionResult | dict, evaluations: list[Evaluation]) -> dict:
    """저장·실시간 평가에서 같은 판정관 입력을 만듭니다."""
    content = draft.model_dump(mode="json") if isinstance(draft, DecisionResult) else draft
    return {
        "draft": {key: content[key] for key in ("summary", "recommendations", "not_recommended")},
        "evaluations": [
            e.model_dump(mode="json", exclude={"request_id", "source", "notes"})
            for e in evaluations
            if e.source == "model"
        ],
        "failed_evaluators": [e.evaluator for e in evaluations if e.source == "failed"],
    }


async def generate_evaluation(
    system_prompt: str, input_json: str, *, settings: LLMSettings
) -> dict:
    return await complete_json(system_prompt, input_json, settings)


def evaluation_input(
    request: DecisionRequest, draft: DecisionResult, allowed: list[EvaluationRequest]
) -> dict:
    context = build_context(request, briefs=[], answers=[])
    codes = {item.category.code for item in [*draft.recommendations, *draft.not_recommended]}
    return {
        "draft": draft.model_dump(
            mode="json", include={"summary", "recommendations", "not_recommended"}
        ),
        "industry_digest": [row for row in context["industry_digest"] if row["code"] in codes],
        **{key: context[key] for key in ("neighborhood", "sources", "map_context")},
        "allowed_requests": allowed,
    }


def check_comments(
    raw: object,
    request: DecisionRequest,
    allowed: list[EvaluationRequest],
    *,
    request_id: str,
    evaluator: EvaluatorId,
) -> Evaluation:
    if not isinstance(raw, dict) or raw.get("verdict") not in ("agree", "conditional", "oppose"):
        return Evaluation(
            request_id=request_id, evaluator=evaluator, source="failed", notes=["형식 오류"]
        )
    paths = {
        a.agent_id: index_paths(a.data) for a in request.analyses if a.status in {"ok", "partial"}
    }
    observation = request.map_observation
    map_data = (
        observation.data.model_dump(mode="json")
        if observation and observation.status != "error"
        else None
    )
    comments: list[EvaluationComment] = []
    invalid = 0
    for item in raw["comments"][:4] if isinstance(raw.get("comments"), list) else []:
        try:
            if not isinstance(item, dict):
                raise ValueError
            item = {**item, "index": len(comments)}
            if item.get("request", "none") not in allowed:
                item["request"] = "none"
            comment = EvaluationComment.model_validate(item)
        except (ValidationError, ValueError):
            invalid += 1
            continue
        comment.evidence = [
            e
            for e in comment.evidence
            if (
                bool(
                    map_data is not None and valid_map_path(e.path, comment.industry_code, map_data)
                )
                if e.agent_id == "map_analysis"
                else e.path in paths.get(e.agent_id, {})
                and paths[e.agent_id][e.path] in (None, comment.industry_code)
            )
        ]
        comments.append(comment)
    return Evaluation(
        request_id=request_id,
        evaluator=evaluator,
        source="model",
        verdict=raw["verdict"],
        comments=comments,
        notes=[f"형식 오류 지적 {invalid}개 제외"] if invalid else [],
    )


async def evaluate_draft(
    evaluator: EvaluatorId,
    request: DecisionRequest,
    draft: DecisionResult,
    *,
    generate: GenerateEvaluation,
    allowed: list[EvaluationRequest],
    timeout: float,  # noqa: ASYNC109 -- 평가자 공개 계약의 호출별 제한시간입니다.
) -> Evaluation:
    request = DecisionRequest.model_validate(request)
    draft = DecisionResult.model_validate(draft)
    if draft.request_id != request.request_id:
        raise ValueError("초안과 원자료의 요청 식별자가 다릅니다.")
    payload = {"evaluator": evaluator, **evaluation_input(request, draft, allowed)}
    try:
        async with asyncio.timeout(timeout):
            prompt = await asyncio.to_thread(
                files(__package__).joinpath("prompt.md").read_text, encoding="utf-8"
            )
            with llm_scope(current_scope()[0], "evaluator." + evaluator):
                raw = await generate(prompt, json.dumps(payload, ensure_ascii=False))
    except TimeoutError:
        note = "시간 초과"
    except (BudgetStorageError, OSError, asyncio.CancelledError):
        raise
    except Exception as exc:
        log_exception(logger, "평가자 모델 응답 실패", exc)
        note = "평가 실패"
    else:
        return check_comments(
            raw, request, allowed, request_id=request.request_id, evaluator=evaluator
        )
    return Evaluation(
        request_id=request.request_id, evaluator=evaluator, source="failed", notes=[note]
    )
