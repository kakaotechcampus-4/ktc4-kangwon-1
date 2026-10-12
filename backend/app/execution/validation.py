"""공통 실행 제한시간 검증입니다."""

import math

from pydantic import TypeAdapter

from app.execution.types import ExecutionState
from app.llm.budget import EVALUATED_MAX_CALLS, MAX_CALLS

_EXECUTION_ADAPTER = TypeAdapter(ExecutionState)


def validate_timeout(value: float) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("실행 제한시간은 유한한 양수여야 합니다.")


def validate_execution_state(state: ExecutionState) -> None:
    """빈 옛 상태는 허용하되 저장된 예산·시간의 손상은 보정하지 않습니다."""
    _EXECUTION_ADAPTER.validate_python(state, strict=True)
    if "time_limit" in state:
        validate_timeout(state["time_limit"])
    elapsed = state.get("elapsed_seconds", 0)
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("누적 실행 시간이 올바르지 않습니다.")
    if "budget" in state:
        budget = state["budget"]
        used = budget.get("used")
        limit = (
            EVALUATED_MAX_CALLS if state.get("capabilities", {}).get("evaluators") else MAX_CALLS
        )
        if (
            type(used) is not int
            or not 0 <= used <= limit
            or not isinstance(budget.get("calls"), list)
        ):
            raise ValueError("모델 호출 예산이 올바르지 않습니다.")
        attempts: set[int] = set()
        for call in budget["calls"]:
            if not isinstance(call, dict):
                raise ValueError("모델 호출 예산이 올바르지 않습니다.")
            attempt = call.get("attempt")
            if type(attempt) is not int or not 1 <= attempt <= used or attempt in attempts:
                raise ValueError("모델 호출 예산이 올바르지 않습니다.")
            attempts.add(attempt)
    if "evaluation_skipped" in state and state["evaluation_skipped"] not in {"no_data", "budget"}:
        raise ValueError("알 수 없는 평가 생략 사유입니다.")
    if "evaluation_start_round" in state and state["evaluation_start_round"] < 0:
        raise ValueError("저장 평가 라운드가 올바르지 않습니다.")
