"""초안 평가 노드입니다."""

from __future__ import annotations

from app.agents.evaluators.agent import _evaluate_prepared, prepare_evaluation_inputs
from app.agents.orchestration.deps import GraphDeps
from app.agents.orchestration.state import GraphState, GraphUpdate
from app.agents.orchestration.workflow import collect
from app.schemas import (
    EVALUATOR_IDS,
    DecisionRequest,
    DecisionResult,
    EvaluationRequest,
)


async def evaluate_draft_node(state: GraphState, *, deps: GraphDeps) -> GraphUpdate:
    draft = state["outcome"]
    assert isinstance(draft, DecisionResult)
    request = DecisionRequest(
        request_id=deps.request_id,
        address=deps.address,
        analyses=state["analyses"],
        map_observation=state.get("map_observation"),
    )
    allowed: list[EvaluationRequest] = ["none"]
    if deps.map_lookup and not (
        state.get("map_queries") or state.get("map_observation") or state["map_done"]
    ):
        allowed.append("map_lookup")
    if deps.supplements and not (state["supplement_done"] or state.get("supplement_context")):
        allowed.append("supplement")
    if deps.mode == "multi_agent" and not deps.retry_only:
        allowed.append("ask_specialists")
    if deps.allow_questions:
        allowed.append("ask_user")

    prepared = prepare_evaluation_inputs(request, draft, allowed)

    async def one(role):
        assert deps.generate_evaluators is not None
        await deps.step("evaluate." + role, "started")
        result = await _evaluate_prepared(
            role,
            prepared,
            generate=deps.generate_evaluators[role],
            timeout_seconds=deps.agent_timeout,
        )
        await deps.step(
            "evaluate." + role,
            "completed",
            source=result.source,
            verdict=result.verdict,
            comments=len(result.comments),
        )
        return result

    evaluations = await collect(one(role) for role in EVALUATOR_IDS)
    if deps.hooks.on_evaluation:
        await deps.hooks.on_evaluation(draft, evaluations)
    successful = [e for e in evaluations if e.source == "model"]
    reason = (
        "all_failed"
        if not successful
        else "no_comments"
        if all(e.verdict == "agree" and not e.comments for e in successful)
        else "comments"
    )
    final_call = reason == "comments"
    await deps.step("evaluate", "completed", final_call=final_call, reason=reason)
    return {
        "draft": draft,
        "evaluations": evaluations,
        "evaluation_start_round": state["consult_round"],
        "final_call": final_call,
    }
