"""분석 결과·보완·최종판단 이력 저장입니다."""

from pathlib import Path
from typing import Any

from app.db.connection import connect
from app.schemas import (
    AGENT_IDS,
    AgentAnalysis,
    DecisionRequest,
    DecisionResult,
    SupplementEvent,
)

from .common import (
    _analysis_row,
    _dumps,
    _insert_agent,
    _now,
    _require_changed,
    _require_running,
    _text,
)
from .map import _get_map_observation


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
        _insert_agent(db, analysis, attempt)


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
        if _get_map_observation(db, result.request_id) != result.map_observation:
            raise ValueError("최종 결과와 저장된 지도 관측이 다릅니다.")
        for agent_id, source_attempt in source_attempts.items():
            row = _analysis_row(db, result.request_id, agent_id, source_attempt)
            if row is None or AgentAnalysis.model_validate_json(row[0]) != sources[agent_id]:
                raise ValueError("판단 원본과 저장된 분석 이력 또는 실행 차수가 일치하지 않습니다.")
        # 이력 추가와 최신 결과 갱신은 함께 성공하거나 함께 취소됩니다.
        db.execute(
            "INSERT INTO decision_results "
            "(request_id, attempt, result_json, source_attempts_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (result.request_id, attempt, payload, _dumps(source_attempts), completed_at),
        )
        changed = db.execute(
            "UPDATE analysis_requests SET result_json = ?, status = 'completed', completed_at = ? "
            "WHERE request_id = ? AND status = 'running'",
            (payload, completed_at, result.request_id),
        )
        _require_changed(changed, "실행 중인 요청이 없습니다.")


# 저장 이력·복원 불변식을 직접 검사하는 테스트용 조회 경로를 유지합니다.
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


def list_agent_results(
    request_id: str, *, db_path: str | Path | None = None
) -> list[dict[str, Any]]:
    with connect(db_path) as db:
        rows = db.execute(
            "SELECT * FROM agent_results WHERE request_id = ? ORDER BY attempt, agent_id",
            (_text(request_id),),
        ).fetchall()
        return [dict(row) for row in rows]


def save_supplement_event(
    event: SupplementEvent, *, db_path: str | Path | None = None
) -> int | None:
    """보완 차수를 발급하고 결과와 이벤트를 함께 저장합니다."""
    event = SupplementEvent.model_validate(event)
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        _require_running(db, event.request_id)
        attempt = None
        if event.analysis is not None:
            analysis = event.analysis
            previous = db.execute(
                "SELECT MAX(attempt) FROM agent_results WHERE request_id=? AND agent_id=?",
                (event.request_id, analysis.agent_id),
            ).fetchone()[0]
            if previous is None:
                raise ValueError("보완할 원본 분석이 없습니다.")
            attempt = previous + 1
            _insert_agent(db, analysis, attempt)
        db.execute(
            "INSERT INTO supplement_events "
            "(request_id, agent_id, status, event_json, created_at, analysis_attempt) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.request_id,
                event.request.agent_id,
                event.status,
                event.model_dump_json(),
                _now(),
                attempt,
            ),
        )
        return attempt


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


def _supplement_sources(db, request_id):
    events, attempts = [], dict.fromkeys(AGENT_IDS, 1)
    for row in db.execute(
        "SELECT event_json,analysis_attempt FROM supplement_events WHERE request_id=? ORDER BY id",
        (request_id,),
    ):
        event = SupplementEvent.model_validate_json(row[0])
        if event.request_id != request_id:
            raise ValueError("보완 요청 식별자가 다릅니다.")
        if event.adopted:
            if row[1] is None:
                raise ValueError("채택한 보완의 분석 차수가 없습니다.")
            attempts[event.request.agent_id] = row[1]
        events.append(event)
    return events, attempts
