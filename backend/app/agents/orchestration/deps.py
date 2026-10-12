"""노드가 공유하는 실행 의존성과 구성 검증입니다."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, fields

from app.agents.decision.agent import GenerateDecision
from app.agents.evaluators.agent import GenerateEvaluation
from app.agents.orchestration import tools, workflow
from app.agents.orchestration.consult import build_specialist_tools
from app.agents.orchestration.supplement import validate_tools
from app.agents.specialists.agent import GenerateSpecialist
from app.execution.validation import validate_timeout
from app.llm.budget import LLMBudget
from app.schemas import (
    AnalysisMode,
    EvaluatorId,
    LandlordAnswer,
    Site,
    SpecialistId,
    validate_radius,
)

from .constants import (
    CONSULT_STEPS,
    EVALUATOR_RESERVE,
)
from .state import RunHooks
from .validation import (
    validate_address,
    validate_agents,
    validate_allow_questions,
    validate_evaluators,
    validate_map_lookup,
    validate_request_id,
    validate_specialists,
    validate_zone_lookup,
)


@dataclass(frozen=True)
class GraphDeps:
    """실행 함수와 설정만 보관하고 요청 상태는 노드가 받습니다."""

    address: str
    request_id: str
    radius_m: int
    resolve: Callable[[str], Awaitable[Site]]
    agents: workflow.AgentRegistry
    generate: GenerateDecision | None
    generate_specialists: dict[SpecialistId, GenerateSpecialist] | None
    generate_evaluators: dict[EvaluatorId, GenerateEvaluation] | None
    supplements: list[tools.SupplementTool]
    map_lookup: tools.MapLookup | None
    find_zones: tools.ZoneLookup | None
    hooks: RunHooks
    budget: LLMBudget | None
    agent_timeout: float
    mode: AnalysisMode
    allow_questions: bool
    evaluators_enabled: bool
    retry_only: bool
    user_answers: list[LandlordAnswer] | None

    def __post_init__(self):
        if self.evaluators_enabled:
            validate_evaluators(self.generate_evaluators)
        if self.mode not in {"single_decision", "multi_agent"}:
            raise ValueError("지원하지 않는 분석 모드입니다.")
        if self.mode == "multi_agent" and not self.retry_only:
            validate_specialists(self.generate_specialists, with_map=self.map_lookup is not None)
        validate_tools(self.supplements)
        validate_radius(self.radius_m)
        validate_timeout(self.agent_timeout)
        validate_address(self.address)
        validate_request_id(self.request_id)
        validate_agents(self.agents)
        if not callable(self.resolve) or (
            self.generate is not None and not callable(self.generate)
        ):
            raise ValueError("주소 변환·최종판단은 호출 가능한 함수여야 합니다.")
        validate_map_lookup(self.map_lookup)
        validate_zone_lookup(self.find_zones)
        validate_allow_questions(self.allow_questions)
        if self.allow_questions and self.hooks.on_questions is None:
            raise ValueError("질문을 저장할 수 없는 실행입니다.")
        if any(
            (hook := getattr(self.hooks, field.name)) is not None and not callable(hook)
            for field in fields(self.hooks)
        ):
            raise ValueError("저장·관찰 콜백은 호출 가능한 함수여야 합니다.")

    async def step(self, stage: str, event: str, **detail) -> None:
        if self.hooks.on_step is not None:
            await self.hooks.on_step(stage, event, detail)

    def expert_calls(self, state):
        return (
            self.budget.open_calls
            - (EVALUATOR_RESERVE if self.evaluators_enabled and "evaluations" not in state else 0)
            if self.budget
            else CONSULT_STEPS
        )

    def registered(self, state, agent_id, query=None):
        return build_specialist_tools(
            state["task"],
            agent_id,
            analyses=state["analyses"],
            supplements=self.supplements,
            map_lookup=self.map_lookup,
            hooks=self.hooks,
            state=state,
            query=query,
            operation_timeout=self.agent_timeout,
        )
