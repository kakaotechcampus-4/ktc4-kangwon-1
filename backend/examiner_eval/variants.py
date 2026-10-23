"""심사위원 V0·V1·V2 구현을 시험 블록 안에서만 바꿔 끼웁니다."""

from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from app.agentic import evaluators, examiner, tools
from examiner_eval import frozen_v1

VARIANTS = ("V0", "V1", "V2")

V0_PERSONA = (
    "심사관입니다. 근거의 원천·기간·반경, L 중복 채점과 전체 업종의 unknown 이유를 검증하세요. "
    "검토 전 공간 초안이 확정 사실이나 점수 근거가 되었는지 확인하세요."
)


def _definitions_with_query_raw(self):
    permitted = (
        tools.EVALUATOR_READS | {"submit_review"}
        if self.actor in tools.EVALUATORS
        else {"get_facts"}
        if self.actor == "advisor"
        else set(tools.TOOL_INPUTS) - {"submit_review"}
    )
    return [d for d in tools.tool_definitions() if d["function"]["name"] in permitted]


@contextmanager
def use_variant(name):
    if name not in VARIANTS:
        raise ValueError(f"알 수 없는 버전: {name}")
    with ExitStack() as stack:
        if name == "V0":
            stack.enter_context(patch.dict(evaluators.PERSONAS, {"examiner": V0_PERSONA}))
            stack.enter_context(patch.object(examiner, "review_packet", evaluators.review_packet))
            stack.enter_context(
                patch.object(tools.ToolExecutor, "definitions", _definitions_with_query_raw)
            )
        elif name == "V1":
            stack.enter_context(patch.dict(evaluators.PERSONAS, {"examiner": frozen_v1.PERSONA}))
            stack.enter_context(patch.object(examiner, "review_packet", frozen_v1.review_packet))
        yield
