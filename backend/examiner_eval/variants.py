"""심사위원 V0·V1·V2 구현을 시험 블록 안에서만 바꿔 끼웁니다."""

from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from app.agentic import aliases, evaluators, examiner, tools
from examiner_eval import frozen_v1

VARIANTS = ("V0", "V1", "V2")

V0_PERSONA = (
    "심사관입니다. 근거의 원천·기간·반경, L 중복 채점과 전체 업종의 unknown 이유를 검증하세요. "
    "검토 전 공간 초안이 확정 사실이나 점수 근거가 되었는지 확인하세요."
)


def _with_query_raw(original):
    def definitions(self):
        defs = original(self)
        if self.actor != "examiner" or any(d["function"]["name"] == "query_raw" for d in defs):
            return defs
        extra = [d for d in tools.tool_definitions() if d["function"]["name"] == "query_raw"]
        return [*defs, *extra[:1]]

    return definitions


@contextmanager
def use_variant(name):
    if name not in VARIANTS:
        raise ValueError(f"알 수 없는 버전: {name}")
    with ExitStack() as stack:
        if name in ("V0", "V1"):
            stack.enter_context(patch.object(aliases, "PERIOD_LABEL_ROLES", frozenset()))
        if name == "V0":
            stack.enter_context(patch.dict(evaluators.PERSONAS, {"examiner": V0_PERSONA}))
            stack.enter_context(patch.object(examiner, "review_packet", evaluators.review_packet))
            stack.enter_context(
                patch.object(
                    tools.ToolExecutor,
                    "definitions",
                    _with_query_raw(tools.ToolExecutor.definitions),
                )
            )
        elif name == "V1":
            stack.enter_context(patch.dict(evaluators.PERSONAS, {"examiner": frozen_v1.PERSONA}))
            stack.enter_context(patch.object(examiner, "review_packet", frozen_v1.review_packet))
        yield
