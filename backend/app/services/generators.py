"""전문가·평가자의 설정과 주입 생성기를 구성합니다."""

from functools import partial

from app.agents.evaluators.agent import generate_evaluation
from app.agents.orchestration.validation import validate_evaluators, validate_specialists
from app.agents.specialists.agent import generate_specialist
from app.schemas import AGENT_IDS, EVALUATOR_IDS


def build_evaluator_generators(settings, injected=None):
    if injected is not None:
        validate_evaluators(injected)
        return injected
    return {
        role: partial(generate_evaluation, settings=settings.evaluator_llm)
        for role in EVALUATOR_IDS
    }


def build_specialist_generators(settings, injected=None, *, with_map=False):
    roles = [*AGENT_IDS, *(["map_analysis"] if with_map else [])]
    if injected is not None:
        validate_specialists(injected, with_map=with_map)
        return injected
    return {
        role: partial(
            generate_specialist, settings=settings.specialist_llms.get(role, settings.decision_llm)
        )
        for role in roles
    }
