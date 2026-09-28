"""요청과 검증된 분석 결과를 짧은 트랜잭션으로 저장합니다."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.schemas import (
    AGENT_IDS,
    AgentAnalysis,
    AgentError,
    AnalysisTask,
    AnswerSubmission,
    DecisionRequest,
    DecisionResult,
    MapLookupPlan,
    MapObservation,
    QuestionSnapshot,
    Site,
    SupplementEvent,
    normalize_answers,
    validate_radius,
)

from .connection import connect


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
        if _get_map_observation(db, result.request_id) != result.map_observation:
            raise ValueError("최종 결과와 저장된 지도 관측이 다릅니다.")
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
    diagnostics: list[dict[str, Any]] | None = None,
    db_path: str | Path | None = None,
) -> None:
    error = AgentError.model_validate(error)
    failed_at = _now()
    with connect(db_path) as db:
        changed = db.execute(
            "UPDATE analysis_requests SET error_json = ?, status = 'failed', completed_at = ? "
            "WHERE request_id = ? AND status IN ('pending', 'running')",
            (error.model_dump_json(), failed_at, _text(request_id)),
        )
        if changed.rowcount != 1:
            raise ValueError("종료할 수 있는 요청이 없습니다.")
        if diagnostics is not None:
            db.execute(
                "INSERT INTO decision_failures VALUES (?, ?, ?, ?)",
                (
                    request_id,
                    failed_at,
                    error.model_dump_json(),
                    json.dumps(diagnostics, ensure_ascii=False, allow_nan=False),
                ),
            )


def list_decision_failures(request_id: str, *, db_path=None) -> list[dict[str, Any]]:
    """실패한 판단은 성공 결과와 분리해서 보존합니다."""
    with connect(db_path) as db:
        return [
            {"failed_at": row[0], "error": json.loads(row[1]), "diagnostics": json.loads(row[2])}
            for row in db.execute(
                "SELECT failed_at,error_json,diagnostics_json FROM decision_failures "
                "WHERE request_id=? ORDER BY failed_at",
                (_text(request_id),),
            )
        ]


def claim_decision_retry(request_id: str, failed_at: str, *, db_path=None) -> dict[str, Any]:
    """검증된 저장 입력을 확보한 한 호출만 실패한 판단을 재시도합니다."""
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM analysis_requests WHERE request_id=?", (request_id,)
        ).fetchone()
        if row is None or row["status"] != "failed" or row["completed_at"] != failed_at:
            raise DecisionRetryConflictError("현재 실패 기록과 재시도 요청이 다릅니다.")
        if json.loads(row["error_json"])["code"] not in {
            "DECISION_CONTRACT_INVALID",
            "DECISION_RETRY_FAILED",
            "ANALYSIS_FAILED",
        }:
            raise DecisionRetryConflictError("이 실패는 최종판단 재시도 대상이 아닙니다.")
        try:
            task = AnalysisTask(
                request_id=request_id,
                site=Site.model_validate_json(row["site_json"]),
                radius_m=row["radius_m"],
            )
            events = [
                SupplementEvent.model_validate_json(r[0])
                for r in db.execute(
                    "SELECT event_json FROM supplement_events WHERE request_id=? ORDER BY id",
                    (request_id,),
                )
            ]
            attempts = dict.fromkeys(AGENT_IDS, 1)
            for event in events:
                if event.request_id != request_id:
                    raise ValueError("보완 요청 식별자가 다릅니다.")
                if event.adopted:
                    attempts[event.request.agent_id] = 2
            analyses = []
            for agent_id, attempt in attempts.items():
                source = db.execute(
                    "SELECT analysis_json FROM agent_results "
                    "WHERE request_id=? AND agent_id=? AND attempt=?",
                    (request_id, agent_id, attempt),
                ).fetchone()
                if source is None:
                    raise ValueError("분석 이력이 부족합니다.")
                analysis = AgentAnalysis.model_validate_json(source[0])
                if (analysis.request_id, analysis.agent_id) != (request_id, agent_id):
                    raise ValueError("분석 식별자가 다릅니다.")
                analyses.append(analysis)
            questions = db.execute(
                "SELECT snapshot_json,answers_json FROM question_sessions WHERE request_id=?",
                (request_id,),
            ).fetchone()
            answers, feedback = [], []
            if questions:
                snapshot = QuestionSnapshot.model_validate_json(questions[0])
                submission = AnswerSubmission.model_validate_json(questions[1])
                answers = normalize_answers(snapshot.waiting, submission).answers
                analyses = _load_question_analyses(db, snapshot)
                feedback = snapshot.feedback
            observation = _get_map_observation(db, request_id)
            if observation and (
                observation.site != task.site or observation.radius_m != task.radius_m
            ):
                raise ValueError("지도 관측 위치가 다릅니다.")
            request = DecisionRequest(
                request_id=request_id,
                address=task.site.input_address,
                analyses=analyses,
                map_observation=observation,
            )
        except (ValueError, TypeError) as exc:
            raise DecisionRetryConflictError(
                "최종판단을 재시도할 저장 입력이 완전하지 않습니다."
            ) from exc
        db.execute(
            "INSERT OR IGNORE INTO decision_failures VALUES (?,?,?,'[]')",
            (request_id, failed_at, row["error_json"]),
        )
        db.execute(
            "UPDATE analysis_requests SET status='running',error_json=NULL,completed_at=NULL "
            "WHERE request_id=?",
            (request_id,),
        )
        return {
            "request": request,
            "site": task.site,
            "answers": answers,
            "feedback": feedback,
            "supplement_context": events,
            "source_attempts": attempts,
        }


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


def _load_question_analyses(
    db: sqlite3.Connection, snapshot: QuestionSnapshot
) -> list[AgentAnalysis]:
    request_id = snapshot.task.request_id
    _get_map_observation(db, request_id)
    row = db.execute("SELECT * FROM analysis_requests WHERE request_id=?", (request_id,)).fetchone()
    if (
        row is None
        or row["site_json"] is None
        or (
            Site.model_validate_json(row["site_json"]) != snapshot.task.site
            or row["radius_m"] != snapshot.task.radius_m
        )
    ):
        raise ValueError("저장된 위치·반경과 질문 작업이 다릅니다.")
    events = [
        SupplementEvent.model_validate_json(r[0])
        for r in db.execute(
            "SELECT event_json FROM supplement_events WHERE request_id=? ORDER BY id", (request_id,)
        )
    ]
    expected = dict.fromkeys(AGENT_IDS, 1)
    for event in events:
        if event.adopted:
            expected[event.request.agent_id] = 2
    if snapshot.source_attempts != expected or snapshot.supplement_done != bool(events):
        raise ValueError("채택된 분석 차수 또는 보완 이력이 다릅니다.")
    analyses = []
    for agent_id in AGENT_IDS:
        source = db.execute(
            "SELECT analysis_json FROM agent_results "
            "WHERE request_id=? AND agent_id=? AND attempt=?",
            (request_id, agent_id, snapshot.source_attempts[agent_id]),
        ).fetchone()
        if source is None:
            raise ValueError("질문이 참조한 분석 이력이 없습니다.")
        analysis = AgentAnalysis.model_validate_json(source[0])
        if (analysis.request_id, analysis.agent_id) != (request_id, agent_id):
            raise ValueError("저장된 분석 식별자가 일치하지 않습니다.")
        analyses.append(analysis)
    return analyses


def load_question_analyses(
    snapshot: QuestionSnapshot, *, db_path: str | Path | None = None
) -> list[AgentAnalysis]:
    snapshot = QuestionSnapshot.model_validate(snapshot)
    with connect(db_path) as db:
        return _load_question_analyses(db, snapshot)


def save_question_snapshot(
    snapshot: QuestionSnapshot, *, db_path: str | Path | None = None
) -> None:
    snapshot = QuestionSnapshot.model_validate(snapshot)
    request_id = snapshot.task.request_id
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        _load_question_analyses(db, snapshot)
        db.execute(
            "INSERT INTO question_sessions(request_id,question_set_id,snapshot_json,created_at) "
            "VALUES (?,?,?,?)",
            (request_id, snapshot.waiting.question_set_id, snapshot.model_dump_json(), _now()),
        )
        changed = db.execute(
            "UPDATE analysis_requests SET status='waiting_for_input' "
            "WHERE request_id=? AND status='running'",
            (request_id,),
        )
        if changed.rowcount != 1:
            raise ValueError("실행 중인 요청만 질문 대기로 전환할 수 있습니다.")


def get_question_snapshot(
    request_id: str, *, db_path: str | Path | None = None
) -> QuestionSnapshot | None:
    with connect(db_path) as db:
        row = db.execute(
            "SELECT snapshot_json FROM question_sessions WHERE request_id=?", (_text(request_id),)
        ).fetchone()
        return QuestionSnapshot.model_validate_json(row[0]) if row else None


def get_question_answers(
    request_id: str, *, db_path: str | Path | None = None
) -> AnswerSubmission | None:
    with connect(db_path) as db:
        row = db.execute(
            "SELECT answers_json FROM question_sessions WHERE request_id=?", (_text(request_id),)
        ).fetchone()
        return AnswerSubmission.model_validate_json(row[0]) if row and row[0] else None


def claim_question_resume(
    submission: AnswerSubmission, *, db_path: str | Path | None = None
) -> bool:
    """한 호출만 재개를 소유합니다. 확정한 답변은 이후 변경하지 않습니다."""
    submission = AnswerSubmission.model_validate(submission)
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT q.*, r.status FROM question_sessions q "
            "JOIN analysis_requests r USING(request_id) WHERE request_id=?",
            (submission.request_id,),
        ).fetchone()
        if row is None:
            raise ValueError("질문 대기 기록이 없습니다.")
        snapshot = QuestionSnapshot.model_validate_json(row["snapshot_json"])
        normalized = normalize_answers(snapshot.waiting, submission)
        if row["answers_json"] is not None:
            if AnswerSubmission.model_validate_json(row["answers_json"]) != normalized:
                raise AnswerConflictError("이미 제출한 답변은 변경할 수 없습니다.")
            if row["status"] not in {"running", "completed", "failed"}:
                raise ValueError("답변과 요청 상태가 일치하지 않습니다.")
            return False
        if row["status"] != "waiting_for_input":
            raise ValueError("질문 대기 중인 요청만 재개할 수 있습니다.")
        _load_question_analyses(db, snapshot)
        db.execute(
            "UPDATE question_sessions SET answers_json=?, answered_at=? WHERE request_id=?",
            (normalized.model_dump_json(), _now(), submission.request_id),
        )
        changed = db.execute(
            "UPDATE analysis_requests SET status='running' "
            "WHERE request_id=? AND status='waiting_for_input'",
            (submission.request_id,),
        )
        if changed.rowcount != 1:
            raise ValueError("질문 재개를 선점하지 못했습니다.")
        return True


def start_map_lookup(
    task: AnalysisTask, plan: MapLookupPlan, *, db_path: str | Path | None = None
) -> None:
    task, plan = AnalysisTask.model_validate(task), MapLookupPlan.model_validate(plan)
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM analysis_requests WHERE request_id=?", (task.request_id,)
        ).fetchone()
        if (
            row is None
            or row["status"] != "running"
            or row["site_json"] is None
            or Site.model_validate_json(row["site_json"]) != task.site
            or row["radius_m"] != task.radius_m
        ):
            raise ValueError("지도 조회할 실행 요청과 위치가 다릅니다.")
        db.execute(
            "INSERT INTO map_observations "
            "(request_id,plan_json,task_json,status,created_at) VALUES (?,?,?,'running',?)",
            (task.request_id, plan.model_dump_json(), task.model_dump_json(), _now()),
        )


def complete_map_lookup(observation: MapObservation, *, db_path: str | Path | None = None) -> None:
    observation = MapObservation.model_validate(observation)
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT m.*, r.status AS request_status FROM map_observations m "
            "JOIN analysis_requests r USING(request_id) WHERE request_id=?",
            (observation.request_id,),
        ).fetchone()
        if row is None or row["status"] != "running" or row["request_status"] != "running":
            raise ValueError("실행 중인 지도 조회가 없습니다.")
        task = AnalysisTask.model_validate_json(row["task_json"])
        plan = MapLookupPlan.model_validate_json(row["plan_json"])
        if (
            observation.site != task.site
            or observation.radius_m != task.radius_m
            or [q.request for q in observation.data.queries.values()] != plan.unique_queries()
        ):
            raise ValueError("지도 관측의 위치·검색 대상이 다릅니다.")
        db.execute(
            "UPDATE map_observations SET status='completed', observation_json=?, "
            "completed_at=? WHERE request_id=?",
            (observation.model_dump_json(), _now(), observation.request_id),
        )


def _get_map_observation(db: sqlite3.Connection, request_id: str) -> MapObservation | None:
    row = db.execute("SELECT * FROM map_observations WHERE request_id=?", (request_id,)).fetchone()
    if row is None:
        return None
    if row["status"] != "completed":
        raise ValueError("지도 관측 저장이 완료되지 않았습니다.")
    observed = MapObservation.model_validate_json(row["observation_json"])
    if observed.request_id != request_id:
        raise ValueError("지도 관측 요청 ID가 다릅니다.")
    return observed


def get_map_observation(
    request_id: str, *, db_path: str | Path | None = None
) -> MapObservation | None:
    with connect(db_path) as db:
        return _get_map_observation(db, _text(request_id))


def get_map_lookup(request_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    """진행 중인 조회도 상태와 공개 관측만 반환합니다."""
    with connect(db_path) as db:
        row = db.execute(
            "SELECT status, observation_json FROM map_observations WHERE request_id=?",
            (_text(request_id),),
        ).fetchone()
        return (
            {"status": row[0], "observation": json.loads(row[1]) if row[1] else None}
            if row
            else None
        )
