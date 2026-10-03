"""저장 트랜잭션 안에서 적용하는 분석 실행 정책입니다."""

import math
from typing import cast

from app.execution.types import ExecutionCapabilities, ExecutionState
from app.llm.budget import EVALUATED_MAX_CALLS, MAX_CALLS
from app.schemas import EVALUATOR_IDS


def retry_allowed(code: str) -> bool:
    return code in {"DECISION_CONTRACT_INVALID", "DECISION_RETRY_FAILED", "ANALYSIS_FAILED"}


class MapAttemptConflict(ValueError):
    """단독 판정의 지도 저장 횟수 제약입니다."""


def validate_map_attempt(mode, last):
    if last and mode == "single_decision":
        raise MapAttemptConflict("기존 모드는 지도 조회를 한 번만 저장합니다.")


def validate_consult_count(count):
    if count >= 3:
        raise ValueError("라운드당 전문가 답변은 최대 세 개입니다.")


def validate_evaluations(evaluations, request_id, message):
    if (
        len(evaluations) != 4
        or {e.evaluator for e in evaluations} != set(EVALUATOR_IDS)
        or any(e.request_id != request_id for e in evaluations)
    ):
        raise ValueError(message)


def update_execution(
    state: ExecutionState,
    *,
    budget=None,
    elapsed_seconds=None,
    capabilities=None,
    evaluation_skipped=None,
    time_limit=None,
):
    """허용된 변경만 적용하며 소비한 예산과 시간은 되돌리지 않습니다."""
    if budget is not None:
        used = budget.get("used")
        if (
            type(used) is not int
            or not state.get("budget", {}).get("used", 0)
            <= used
            <= (
                EVALUATED_MAX_CALLS
                if state.get("capabilities", {}).get("evaluators")
                else MAX_CALLS
            )
            or not isinstance(budget.get("calls"), list)
        ):
            raise ValueError("모델 소비 예산이 올바르지 않습니다.")
        state["budget"] = budget
    if elapsed_seconds is not None:
        if not math.isfinite(elapsed_seconds) or elapsed_seconds < state.get("elapsed_seconds", 0):
            raise ValueError("누적 실행 시간은 줄일 수 없습니다.")
        state["elapsed_seconds"] = elapsed_seconds
    if capabilities is not None:
        if "capabilities" in state and state["capabilities"] != capabilities:
            raise ValueError("등록한 도구 범위를 변경할 수 없습니다.")
        state["capabilities"] = cast(ExecutionCapabilities, capabilities)
    if evaluation_skipped is not None:
        if evaluation_skipped not in {"no_data", "budget"}:
            raise ValueError("알 수 없는 평가 생략 사유입니다.")
        state["evaluation_skipped"] = evaluation_skipped
    if time_limit is not None:
        if (
            not math.isfinite(time_limit)
            or time_limit <= 0
            or state.get("time_limit", time_limit) != time_limit
        ):
            raise ValueError("요청의 실행 제한시간은 양수이며 변경할 수 없습니다.")
        state["time_limit"] = time_limit
