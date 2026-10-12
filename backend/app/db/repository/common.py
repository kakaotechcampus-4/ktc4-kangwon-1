"""저장소 공통 조회·저장 헬퍼와 예외입니다."""

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.schemas import (
    AgentAnalysis,
)


class AnswerConflictError(ValueError):
    """다른 호출이 먼저 확정한 답변과 충돌합니다."""


class DecisionRetryConflictError(ValueError):
    """실패 상태 또는 저장된 입력이 재시도 조건과 다릅니다."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("비어 있지 않은 문자열이 필요합니다.")
    return value.strip()


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _request_row(db: sqlite3.Connection, request_id: str) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM analysis_requests WHERE request_id=?", (request_id,)
    ).fetchone()


def _analysis_row(db: sqlite3.Connection, request_id: str, agent_id: str, attempt: int):
    return db.execute(
        "SELECT analysis_json FROM agent_results WHERE request_id=? AND agent_id=? AND attempt=?",
        (request_id, agent_id, attempt),
    ).fetchone()


def _insert_agent(db: sqlite3.Connection, analysis: AgentAnalysis, attempt: int) -> None:
    db.execute(
        "INSERT INTO agent_results VALUES (?, ?, ?, ?, ?, ?)",
        (
            analysis.request_id,
            analysis.agent_id,
            attempt,
            analysis.status,
            analysis.model_dump_json(),
            _now(),
        ),
    )


def _require_changed(changed, message="실행 중인 요청이 없습니다.") -> None:
    if changed.rowcount != 1:
        raise ValueError(message)


def _require_running(db, request_id, *, multi=False):
    row = _request_row(db, request_id)
    if (
        row is None
        or row["status"] != "running"
        or (multi and row["analysis_mode"] != "multi_agent")
    ):
        raise ValueError(
            "실행 중인 멀티에이전트 요청이 없습니다." if multi else "실행 중인 요청이 없습니다."
        )
    return row
