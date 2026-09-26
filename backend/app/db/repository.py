"""요청과 검증된 분석 결과를 짧은 트랜잭션으로 저장합니다."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.schemas import (
    AgentAnalysis,
    AgentError,
    AnalysisTask,
    DecisionRequest,
    DecisionResult,
    SupplementEvent,
    validate_radius,
)

from .connection import connect


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("비어 있지 않은 문자열이 필요합니다.")
    return value.strip()


def create_request(
    request_id: str,
    address: str,
    *,
    radius_m: int | None = None,
    db_path: str | Path | None = None,
) -> None:
    request_id = _text(request_id)
    _text(address)
    if radius_m is not None:
        radius_m = validate_radius(radius_m)
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO analysis_requests "
            "(request_id, input_address, radius_m, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (request_id, address, radius_m, _now()),
        )


def mark_running(request_id: str, *, db_path: str | Path | None = None) -> None:
    with connect(db_path) as db:
        changed = db.execute(
            "UPDATE analysis_requests SET status = 'running' "
            "WHERE request_id = ? AND status = 'pending'",
            (_text(request_id),),
        )
        if changed.rowcount != 1:
            raise ValueError("대기 중인 요청이 없습니다.")


def save_site(task: AnalysisTask, *, db_path: str | Path | None = None) -> None:
    task = AnalysisTask.model_validate(task)
    with connect(db_path) as db:
        changed = db.execute(
            "UPDATE analysis_requests SET site_json = ? "
            "WHERE request_id = ? AND status = 'running'",
            (task.site.model_dump_json(), task.request_id),
        )
        if changed.rowcount != 1:
            raise ValueError("실행 중인 요청이 없습니다.")


def save_agent(
    analysis: AgentAnalysis,
    *,
    attempt: int = 1,
    db_path: str | Path | None = None,
) -> None:
    analysis = AgentAnalysis.model_validate(analysis)
    if type(attempt) is not int or attempt < 1:
        raise ValueError("실행 차수는 1 이상의 정수여야 합니다.")
    with connect(db_path) as db:
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


def complete_request(
    result: DecisionResult,
    *,
    attempt: int = 1,
    source_attempts: dict[str, int] | None = None,
    db_path: str | Path | None = None,
) -> None:
    result = DecisionResult.model_validate(result)
    # 최종 출력 스키마에서 별도로 검사하지 않는 원본 요청 ID와 중복도 확인합니다.
    DecisionRequest(
        request_id=result.request_id, address=result.address, analyses=result.source_analyses
    )
    if type(attempt) is not int or attempt < 1:
        raise ValueError("판단 차수는 1 이상의 정수여야 합니다.")
    sources: dict[str, AgentAnalysis] = {item.agent_id: item for item in result.source_analyses}
    source_attempts = dict.fromkeys(sources, 1) if source_attempts is None else source_attempts
    if set(source_attempts) != set(sources) or any(
        type(value) is not int or value < 1 for value in source_attempts.values()
    ):
        raise ValueError("판단에 사용한 모든 분석의 실행 차수를 지정해야 합니다.")
    payload, completed_at = result.model_dump_json(), _now()
    with connect(db_path) as db:
        for agent_id, source_attempt in source_attempts.items():
            row = db.execute(
                "SELECT analysis_json FROM agent_results "
                "WHERE request_id = ? AND agent_id = ? AND attempt = ?",
                (result.request_id, agent_id, source_attempt),
            ).fetchone()
            if row is None or AgentAnalysis.model_validate_json(row[0]) != sources[agent_id]:
                raise ValueError("판단 원본과 저장된 분석 이력 또는 실행 차수가 일치하지 않습니다.")
        # 이력 추가와 최신 결과 갱신은 함께 성공하거나 함께 취소됩니다.
        db.execute(
            "INSERT INTO decision_results "
            "(request_id, attempt, result_json, source_attempts_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (result.request_id, attempt, payload, json.dumps(source_attempts), completed_at),
        )
        changed = db.execute(
            "UPDATE analysis_requests SET result_json = ?, status = 'completed', completed_at = ? "
            "WHERE request_id = ? AND status = 'running'",
            (payload, completed_at, result.request_id),
        )
        if changed.rowcount != 1:
            raise ValueError("실행 중인 요청이 없습니다.")


def list_decision_results(
    request_id: str, *, db_path: str | Path | None = None
) -> list[dict[str, Any]]:
    """최종판단 이력을 실행 차수 순서로 반환합니다."""
    with connect(db_path) as db:
        rows = db.execute(
            "SELECT * FROM decision_results WHERE request_id = ? ORDER BY attempt",
            (_text(request_id),),
        ).fetchall()
        return [dict(row) for row in rows]


def fail_request(
    request_id: str,
    error: AgentError,
    *,
    db_path: str | Path | None = None,
) -> None:
    error = AgentError.model_validate(error)
    with connect(db_path) as db:
        changed = db.execute(
            "UPDATE analysis_requests SET error_json = ?, status = 'failed', completed_at = ? "
            "WHERE request_id = ? AND status IN ('pending', 'running')",
            (error.model_dump_json(), _now(), _text(request_id)),
        )
        if changed.rowcount != 1:
            raise ValueError("종료할 수 있는 요청이 없습니다.")


def get_request(request_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as db:
        row = db.execute(
            "SELECT * FROM analysis_requests WHERE request_id = ?", (_text(request_id),)
        ).fetchone()
        return dict(row) if row else None


def list_agent_results(
    request_id: str, *, db_path: str | Path | None = None
) -> list[dict[str, Any]]:
    with connect(db_path) as db:
        rows = db.execute(
            "SELECT * FROM agent_results WHERE request_id = ? ORDER BY attempt, agent_id",
            (_text(request_id),),
        ).fetchall()
        return [dict(row) for row in rows]


def save_supplement_event(event: SupplementEvent, *, db_path: str | Path | None = None) -> None:
    """보완 결과 2차 이력과 이벤트를 한 트랜잭션으로 저장합니다."""
    event = SupplementEvent.model_validate(event)
    with connect(db_path) as db:
        row = db.execute(
            "SELECT status FROM analysis_requests WHERE request_id = ?",
            (event.request_id,),
        ).fetchone()
        if row is None or row[0] != "running":
            raise ValueError("실행 중인 요청이 없습니다.")
        if event.analysis is not None:
            analysis = event.analysis
            db.execute(
                "INSERT INTO agent_results VALUES (?, ?, 2, ?, ?, ?)",
                (
                    event.request_id,
                    analysis.agent_id,
                    analysis.status,
                    analysis.model_dump_json(),
                    _now(),
                ),
            )
        db.execute(
            "INSERT INTO supplement_events "
            "(request_id, agent_id, status, event_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                event.request_id,
                event.request.agent_id,
                event.status,
                event.model_dump_json(),
                _now(),
            ),
        )


def list_supplement_events(
    request_id: str, *, db_path: str | Path | None = None
) -> list[dict[str, Any]]:
    with connect(db_path) as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT * FROM supplement_events WHERE request_id = ? ORDER BY id",
                (_text(request_id),),
            ).fetchall()
        ]
