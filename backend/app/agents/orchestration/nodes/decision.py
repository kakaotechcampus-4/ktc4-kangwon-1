"""판정과 다음 단계 선택 노드입니다."""

from __future__ import annotations

from typing import Any

from app.agents.decision import agent as decision
from app.agents.evaluators.agent import decision_evaluation
from app.agents.orchestration.constants import (
    EVALUATION_CONSULT_ROUNDS,
    EVALUATOR_RESERVE,
    INITIAL_CONSULT_ROUNDS,
    MIN_EXPERT_CALLS,
)
from app.agents.orchestration.deps import GraphDeps
from app.agents.orchestration.state import GraphState
from app.schemas import (
    AGENT_IDS,
    QUESTION_FIELDS,
    ConsultPlan,
    DecisionRequest,
    DecisionResult,
    EvaluationLogEntry,
    MapLookupPlan,
    QuestionPlan,
    SupplementPlan,
)


def action_of(outcome) -> str:
    """최종판단이 고른 다음 행동 이름입니다."""
    if isinstance(outcome, ConsultPlan):
        return "ask_specialists"
    if isinstance(outcome, SupplementPlan):
        return "supplement"
    if isinstance(outcome, MapLookupPlan):
        return "map_lookup"
    if isinstance(outcome, QuestionPlan):
        return "ask_user"
    return "final"


async def evaluate_decision(state: GraphState, *, deps: GraphDeps) -> GraphState:
    phase = (
        {"phase": "final" if "evaluations" in state else "draft"} if deps.evaluators_enabled else {}
    )
    await deps.step("decision", "started", **phase)
    result = await _evaluate(state, deps=deps)
    await deps.step("decision", "completed", action=action_of(result["outcome"]), **phase)
    if (
        deps.evaluators_enabled
        and "evaluations" not in state
        and isinstance(result["outcome"], DecisionResult)
    ):
        reason = (
            "no_data"
            if result["outcome"].status == "no_data"
            else "budget"
            if deps.budget is not None and deps.budget.open_calls < EVALUATOR_RESERVE
            else None
        )
        if reason:
            await deps.step("evaluate", "completed", skipped=reason)
            result["final_call"] = False
    return result


def remaining_rounds(state):
    ceiling = (
        state.get("evaluation_start_round", 0) + EVALUATION_CONSULT_ROUNDS
        if "evaluations" in state
        else INITIAL_CONSULT_ROUNDS
    )
    return max(0, ceiling - state["consult_round"])


async def evaluate_with_log(state, request, **kwargs):
    entries: list[EvaluationLogEntry] = []
    extra: dict[str, Any] = {}
    if "evaluations" in state:
        extra = {
            "evaluation": decision_evaluation(state["draft"], state["evaluations"]),
            "evaluation_log": entries,
        }
    outcome = await decision.evaluate(request, **kwargs, **extra)
    return outcome, entries


async def judge(state, request, *, deps: GraphDeps, **kwargs):
    outcome, entries = await evaluate_with_log(state, request, **kwargs)
    if (
        "evaluations" in state
        and isinstance(outcome, DecisionResult)
        and deps.hooks.on_evaluation_log
    ):
        await deps.hooks.on_evaluation_log(entries)
    return outcome


async def _evaluate(state: GraphState, *, deps: GraphDeps) -> GraphState:
    task = state["task"]
    request = DecisionRequest(
        request_id=task.request_id,
        address=task.site.input_address,
        analyses=state["analyses"],
        map_observation=state.get("map_observation"),
    )
    questions_allowed = deps.allow_questions and (
        not deps.evaluators_enabled or "evaluations" in state
    )
    if deps.mode == "multi_agent":
        specialists = [*AGENT_IDS, *(["map_analysis"] if deps.map_lookup else [])]
        if (
            deps.retry_only
            or not remaining_rounds(state)
            or deps.budget is not None
            and deps.expert_calls(state) < MIN_EXPERT_CALLS
        ):
            specialists = []
        outcome = await judge(
            state,
            request,
            deps=deps,
            generate=deps.generate,
            site=task.site,
            user_answers=deps.user_answers,
            question_fields=list(QUESTION_FIELDS)
            if questions_allowed and (deps.budget is None or deps.budget.open_calls > 0)
            else None,
            feedback=state.get("feedback"),
            supplement_context=state.get("supplement_context"),
            deliberation={
                "briefs": state["briefs"],
                "answers": state["answers"],
                "specialists": specialists,
                "consult_round": state["consult_round"],
                **(
                    {"remaining_consult_rounds": remaining_rounds(state)}
                    if deps.evaluators_enabled
                    else {}
                ),
            },
        )
        return {"outcome": outcome}
    if state["supplement_done"]:
        outcome = await judge(
            state,
            request,
            deps=deps,
            generate=deps.generate,
            feedback=state["feedback"],
            user_answers=deps.user_answers,
            supplement_context=state["supplement_context"],
            question_fields=list(QUESTION_FIELDS) if questions_allowed else None,
            site=task.site if deps.allow_questions else None,
            allow_map_lookup=deps.map_lookup is not None and not state["map_done"],
        )
        if isinstance(outcome, SupplementPlan):
            raise ValueError("보완 라운드를 추가 실행할 수 없습니다.")
        return {"outcome": outcome}
    sources = {item.agent_id: item for item in state["analyses"]}
    operations = [
        tool.operation
        for tool in deps.supplements
        if tool.eligible(
            task.model_copy(deep=True),
            sources[tool.operation.agent_id].model_copy(deep=True),
        )
    ]
    outcome = await judge(
        state,
        request,
        deps=deps,
        generate=deps.generate,
        operations=operations,
        user_answers=deps.user_answers,
        question_fields=list(QUESTION_FIELDS) if questions_allowed else None,
        site=task.site if deps.allow_questions else None,
        allow_map_lookup=deps.map_lookup is not None and not state["map_done"],
    )
    return {"outcome": outcome, "operations": operations}


def route(state, *, deps: GraphDeps):
    outcome = state["outcome"]
    if isinstance(outcome, ConsultPlan):
        return "consult"
    if isinstance(outcome, MapLookupPlan):
        return "map"
    if isinstance(outcome, SupplementPlan):
        return "supplement"
    if isinstance(outcome, QuestionPlan):
        return "question"
    if deps.evaluators_enabled and "evaluations" not in state and state.get("final_call", True):
        return "evaluate"
    return "final"
