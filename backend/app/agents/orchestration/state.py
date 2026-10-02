"""그래프의 요청 상태와 저장 콜백 계약입니다."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypedDict, cast

from app.agents.orchestration import tools
from app.agents.orchestration.supplement import OnSupplement
from app.schemas import (
    AgentAnalysis,
    AgentBrief,
    AnalysisMode,
    AnalysisTask,
    ConsultPlan,
    DecisionResult,
    Evaluation,
    EvaluationLogEntry,
    MapLookupPlan,
    MapObservation,
    MapQuery,
    QuestionPlan,
    SpecialistAnswer,
    SupplementEvent,
    SupplementOperation,
    SupplementPlan,
    WaitingForInput,
)


class GraphState(TypedDict, total=False):
    """요청별 데이터만 보관하며 실행 함수와 비밀키는 포함하지 않습니다."""

    task: AnalysisTask
    analyses: list[AgentAnalysis]
    outcome: (
        DecisionResult
        | SupplementPlan
        | QuestionPlan
        | WaitingForInput
        | MapLookupPlan
        | ConsultPlan
    )
    map_done: bool
    map_observation: MapObservation | None
    operations: list[SupplementOperation]
    supplement_done: bool
    feedback: list[str]
    supplement_context: list[SupplementEvent]
    briefs: list[AgentBrief]
    answers: list[SpecialistAnswer]
    consult_round: int
    map_queries: list[MapQuery]
    draft: DecisionResult
    evaluations: list[Evaluation]
    evaluation_start_round: int
    final_call: bool


def normalize_resume_state(state: Mapping[str, Any], *, mode: AnalysisMode) -> GraphState:
    """옛 중첩 상태를 읽되 이전 모드의 읽기 우선순위를 유지합니다."""
    restored = dict(state)
    legacy = restored.pop("context", {})
    for key in ("map_observation", "map_queries", "feedback", "supplement_context"):
        if key in legacy and (mode == "multi_agent" or key not in restored):
            restored[key] = legacy[key]
    return cast(GraphState, restored)


@dataclass(frozen=True)
class RunHooks:
    """서비스가 관리하는 저장·관찰 콜백입니다."""

    on_task_prepared: Callable[[AnalysisTask], Awaitable[None]] | None = None
    on_analysis_completed: Callable[[AgentAnalysis], Awaitable[None]] | None = None
    on_supplement: OnSupplement | None = None
    on_map_requested: tools.OnMapRequested | None = None
    on_map_completed: tools.OnMapCompleted | None = None
    on_map_result: Callable[[MapObservation, bool], Awaitable[None]] | None = None
    on_brief: Callable[[AgentBrief], Awaitable[None]] | None = None
    on_consult: Callable[[SpecialistAnswer], Awaitable[None]] | None = None
    on_questions: (
        Callable[[AnalysisTask, WaitingForInput, bool, list[str]], Awaitable[None]] | None
    ) = None
    # 진행 화면용 단계 이벤트입니다. detail에는 코드가 정한 요약만 넣습니다.
    on_step: Callable[[str, str, dict], Awaitable[None]] | None = None
    on_evaluation: Callable[[DecisionResult, list[Evaluation]], Awaitable[None]] | None = None
    on_evaluation_log: Callable[[list[EvaluationLogEntry]], Awaitable[None]] | None = None


def initial_state(resume_state, *, mode: AnalysisMode) -> GraphState:
    """새 실행의 빈 상태에 저장된 재개 자료만 덮어씁니다."""
    initial: GraphState = {
        "supplement_done": False,
        "map_done": False,
        "briefs": [],
        "answers": [],
        "consult_round": 0,
        "map_queries": [],
        "feedback": [],
        "supplement_context": [],
    }
    if resume_state is not None:
        initial.update(normalize_resume_state(resume_state, mode=mode))
    return initial
