"""요청과 검증된 분석 결과를 짧은 트랜잭션으로 저장합니다."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.db.types import (
    AnalysisEvent,
    DecisionFailure,
    DeliberationState,
    ExecutionState,
    MapLookupState,
    ResumeBundle,
)
from app.industries.catalog import CATALOG_VERSION
from app.schemas import (
    AGENT_IDS,
    EVALUATOR_IDS,
    AgentAnalysis,
    AgentBrief,
    AgentError,
    AnalysisMode,
    AnalysisTask,
    AnswerSubmission,
    DecisionRequest,
    DecisionResult,
    Evaluation,
    EvaluationLogEntry,
    MapLookupPlan,
    MapObservation,
    QuestionSnapshot,
    QuestionSnapshotV2,
    Site,
    SpecialistAnswer,
    SupplementEvent,
    normalize_answers,
    validate_radius,
)
from app.services import execution_policy as policy

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


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def create_request(
    request_id: str,
    address: str,
    *,
    radius_m: int | None = None,
    analysis_mode: AnalysisMode = "single_decision",
    db_path: str | Path | None = None,
) -> None:
    request_id = _text(request_id)
    _text(address)
    if analysis_mode not in {"single_decision", "multi_agent"}:
        raise ValueError("지원하지 않는 분석 모드입니다.")
    if radius_m is not None:
        radius_m = validate_radius(radius_m)
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO analysis_requests "
            "(request_id, input_address, radius_m, catalog_version, "
            "analysis_mode, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (request_id, address, radius_m, CATALOG_VERSION, analysis_mode, _now()),
        )


def mark_running(request_id: str, *, db_path: str | Path | None = None) -> None:
    with connect(db_path) as db:
        changed = db.execute(
            "UPDATE analysis_requests SET status = 'running' "
            "WHERE request_id = ? AND status = 'pending'",
            (_text(request_id),),
        )
        _require_changed(changed, "대기 중인 요청이 없습니다.")


def save_site(task: AnalysisTask, *, db_path: str | Path | None = None) -> None:
    task = AnalysisTask.model_validate(task)
    with connect(db_path) as db:
        changed = db.execute(
            "UPDATE analysis_requests SET site_json = ? "
            "WHERE request_id = ? AND status = 'running'",
            (task.site.model_dump_json(), task.request_id),
        )
        _require_changed(changed, "실행 중인 요청이 없습니다.")


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


def fail_request(
    request_id: str,
    error: AgentError,
    *,
    diagnostics: list[dict[str, Any]] | None = None,
    db_path: str | Path | None = None,
) -> None:
    error = AgentError.model_validate(error)
    request_id = _text(request_id)
    failed_at = _now()
    with connect(db_path) as db:
        changed = db.execute(
            "UPDATE analysis_requests SET error_json = ?, status = 'failed', completed_at = ? "
            "WHERE request_id = ? AND status IN ('pending', 'running')",
            (error.model_dump_json(), failed_at, request_id),
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
                    _dumps(diagnostics),
                ),
            )


def list_decision_failures(
    request_id: str, *, db_path: str | Path | None = None
) -> list[DecisionFailure]:
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


def claim_decision_retry(
    request_id: str, failed_at: str, *, db_path: str | Path | None = None
) -> ResumeBundle:
    """검증된 저장 입력을 확보한 한 호출만 실패한 판단을 재시도합니다."""
    request_id = _text(request_id)
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = _request_row(db, request_id)
        if row is None or row["status"] != "failed" or row["completed_at"] != failed_at:
            raise DecisionRetryConflictError("현재 실패 기록과 재시도 요청이 다릅니다.")
        if row["catalog_version"] != CATALOG_VERSION:
            raise DecisionRetryConflictError(
                "업종표 버전이 다르거나 확인되지 않아 새 분석이 필요합니다."
            )
        if not policy.retry_allowed(json.loads(row["error_json"])["code"]):
            raise DecisionRetryConflictError("이 실패는 최종판단 재시도 대상이 아닙니다.")
        try:
            context = _load_resume_context(db, request_id)
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
        return context


def get_request(request_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as db:
        row = _request_row(db, _text(request_id))
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


def _load_question_analyses(
    db: sqlite3.Connection, snapshot: QuestionSnapshot
) -> list[AgentAnalysis]:
    request_id = snapshot.task.request_id
    _get_map_observation(db, request_id)
    row = _request_row(db, request_id)
    if (
        row is None
        or row["site_json"] is None
        or (
            Site.model_validate_json(row["site_json"]) != snapshot.task.site
            or row["radius_m"] != snapshot.task.radius_m
        )
    ):
        raise ValueError("저장된 위치·반경과 질문 작업이 다릅니다.")
    events, expected = _supplement_sources(db, request_id)
    if snapshot.source_attempts != expected or snapshot.supplement_done != bool(events):
        raise ValueError("채택된 분석 차수 또는 보완 이력이 다릅니다.")
    if isinstance(snapshot, QuestionSnapshotV2):
        state = _deliberation(db, request_id)
        if (
            row["analysis_mode"] != "multi_agent"
            or set(snapshot.brief_agents) != {b.agent_id for b in state["briefs"]}
            or snapshot.consult_round != state["consult_round"]
            or snapshot.map_attempt != state["map_attempt"]
            or snapshot.llm_calls != state["execution"].get("budget", {}).get("used", 0)
            or snapshot.elapsed_seconds != state["execution"].get("elapsed_seconds", 0)
        ):
            raise ValueError("질문이 참조한 전문가·지도·예산 이력이 다릅니다.")
    elif row["analysis_mode"] != "single_decision":
        raise ValueError("질문 버전과 실행 모드가 다릅니다.")
    analyses = []
    for agent_id in AGENT_IDS:
        source = _analysis_row(db, request_id, agent_id, snapshot.source_attempts[agent_id])
        if source is None:
            raise ValueError("질문이 참조한 분석 이력이 없습니다.")
        analysis = AgentAnalysis.model_validate_json(source[0])
        if (analysis.request_id, analysis.agent_id) != (request_id, agent_id):
            raise ValueError("저장된 분석 식별자가 일치하지 않습니다.")
        analyses.append(analysis)
    return analyses


# 저장 이력·복원 불변식을 직접 검사하는 테스트용 조회 경로를 유지합니다.
def load_question_analyses(
    snapshot: QuestionSnapshot, *, db_path: str | Path | None = None
) -> list[AgentAnalysis]:
    snapshot = parse_snapshot(snapshot)
    with connect(db_path) as db:
        return _load_question_analyses(db, snapshot)


def save_question_snapshot(
    snapshot: QuestionSnapshot, *, db_path: str | Path | None = None
) -> None:
    snapshot = parse_snapshot(snapshot)
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
        return parse_snapshot(row[0]) if row else None


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
            "SELECT q.*, r.status, r.catalog_version FROM question_sessions q "
            "JOIN analysis_requests r USING(request_id) WHERE request_id=?",
            (submission.request_id,),
        ).fetchone()
        if row is None:
            raise ValueError("질문 대기 기록이 없습니다.")
        snapshot = parse_snapshot(row["snapshot_json"])
        normalized = normalize_answers(snapshot.waiting, submission)
        if row["answers_json"] is not None:
            if AnswerSubmission.model_validate_json(row["answers_json"]) != normalized:
                raise AnswerConflictError("이미 제출한 답변은 변경할 수 없습니다.")
            if row["status"] not in {"running", "completed", "failed"}:
                raise ValueError("답변과 요청 상태가 일치하지 않습니다.")
            return False
        if row["status"] != "waiting_for_input":
            raise ValueError("질문 대기 중인 요청만 재개할 수 있습니다.")
        if row["catalog_version"] != CATALOG_VERSION:
            raise AnswerConflictError("업종표 버전이 다르거나 확인되지 않아 새 분석이 필요합니다.")
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
) -> int:
    task, plan = AnalysisTask.model_validate(task), MapLookupPlan.model_validate(plan)
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = _request_row(db, task.request_id)
        if (
            row is None
            or row["status"] != "running"
            or row["site_json"] is None
            or Site.model_validate_json(row["site_json"]) != task.site
            or row["radius_m"] != task.radius_m
        ):
            raise ValueError("지도 조회할 실행 요청과 위치가 다릅니다.")
        last = db.execute(
            "SELECT MAX(attempt) FROM map_observations WHERE request_id=?", (task.request_id,)
        ).fetchone()[0]
        policy.validate_map_attempt(row["analysis_mode"], last)
        attempt = (last or 0) + 1
        db.execute(
            "INSERT INTO map_observations "
            "(request_id,attempt,plan_json,task_json,status,created_at) "
            "VALUES (?,?,?,?,'running',?)",
            (task.request_id, attempt, plan.model_dump_json(), task.model_dump_json(), _now()),
        )
        return attempt


def complete_map_lookup(
    observation: MapObservation, *, adopted: bool = True, db_path: str | Path | None = None
) -> None:
    observation = MapObservation.model_validate(observation)
    if type(adopted) is not bool:
        raise ValueError("지도 채택 여부가 올바르지 않습니다.")
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT m.*, r.status AS request_status FROM map_observations m "
            "JOIN analysis_requests r USING(request_id) "
            "WHERE request_id=? AND m.status='running'",
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
            "UPDATE map_observations SET status='completed', observation_json=?, adopted=?, "
            "completed_at=? WHERE request_id=? AND attempt=?",
            (
                observation.model_dump_json(),
                int(adopted),
                _now(),
                observation.request_id,
                row["attempt"],
            ),
        )


def _get_map_observation(db: sqlite3.Connection, request_id: str) -> MapObservation | None:
    if db.execute(
        "SELECT 1 FROM map_observations WHERE request_id=? AND status='running'", (request_id,)
    ).fetchone():
        raise ValueError("지도 관측 저장이 완료되지 않았습니다.")
    row = db.execute(
        "SELECT * FROM map_observations WHERE request_id=? AND adopted=1 "
        "ORDER BY attempt DESC LIMIT 1",
        (request_id,),
    ).fetchone()
    if row is None:
        return None
    if row["status"] != "completed":
        raise ValueError("지도 관측 저장이 완료되지 않았습니다.")
    observed = MapObservation.model_validate_json(row["observation_json"])
    if observed.request_id != request_id:
        raise ValueError("지도 관측 요청 ID가 다릅니다.")
    return observed


# 저장 이력·복원 불변식을 직접 검사하는 테스트용 조회 경로를 유지합니다.
def get_map_observation(
    request_id: str, *, db_path: str | Path | None = None
) -> MapObservation | None:
    with connect(db_path) as db:
        return _get_map_observation(db, _text(request_id))


def get_map_lookup(request_id: str, *, db_path: str | Path | None = None) -> MapLookupState | None:
    """진행 중인 조회도 상태와 공개 관측만 반환합니다."""
    with connect(db_path) as db:
        row = db.execute(
            "SELECT status, observation_json FROM map_observations WHERE request_id=? "
            "ORDER BY attempt DESC LIMIT 1",
            (_text(request_id),),
        ).fetchone()
        return (
            {
                "status": row[0],
                "observation": (
                    latest.model_dump(mode="json")
                    if (latest := _get_map_observation(db, request_id))
                    else None
                )
                if row[0] == "completed"
                else None,
            }
            if row
            else None
        )


def load_resume_context(request_id: str, *, db_path: str | Path | None = None) -> ResumeBundle:
    """질문 재개와 실패 재시도가 동일한 저장 자료를 복원합니다."""
    with connect(db_path) as db:
        return _load_resume_context(db, request_id)


def _load_resume_context(db: sqlite3.Connection, request_id: str) -> ResumeBundle:
    row = _request_row(db, request_id)
    if row is None or row["catalog_version"] != CATALOG_VERSION:
        raise ValueError("요청 또는 현재 업종표 버전의 저장 자료가 없습니다.")
    task = AnalysisTask(
        request_id=request_id,
        site=Site.model_validate_json(row["site_json"]),
        radius_m=row["radius_m"],
    )
    events, attempts = _supplement_sources(db, request_id)
    analyses = []
    for agent_id, attempt in attempts.items():
        source = _analysis_row(db, request_id, agent_id, attempt)
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
        snapshot = parse_snapshot(questions[0])
        submission = AnswerSubmission.model_validate_json(questions[1])
        answers = normalize_answers(snapshot.waiting, submission).answers
        if not isinstance(snapshot, QuestionSnapshotV2):
            analyses = _load_question_analyses(db, snapshot)
        feedback = snapshot.feedback
    observation = _get_map_observation(db, request_id)
    if observation and (observation.site != task.site or observation.radius_m != task.radius_m):
        raise ValueError("지도 관측 위치가 다릅니다.")
    request = DecisionRequest(
        request_id=request_id,
        address=task.site.input_address,
        analyses=analyses,
        map_observation=observation,
    )
    return {
        "request": request,
        "site": task.site,
        "answers": answers,
        "feedback": feedback,
        "supplement_context": events,
        "source_attempts": attempts,
        "task": task,
        "analysis_mode": row["analysis_mode"],
        **_deliberation(db, request_id),
    }


def parse_snapshot(value: QuestionSnapshot | dict | str) -> QuestionSnapshot | QuestionSnapshotV2:
    data = (
        value.model_dump(mode="json")
        if isinstance(value, QuestionSnapshot)
        else json.loads(value)
        if isinstance(value, str)
        else value
    )
    model = QuestionSnapshotV2 if data.get("version") == 2 else QuestionSnapshot
    return model.model_validate(data)


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


def update_execution_state(
    request_id: str,
    *,
    budget: dict | None = None,
    elapsed_seconds: float | None = None,
    capabilities: dict | None = None,
    evaluation_skipped: str | None = None,
    time_limit: float | None = None,
    db_path: str | Path | None = None,
) -> None:
    """소비 예산·활성 실행 시간은 되돌리지 않고 저장합니다."""
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = _require_running(db, request_id)
        state: ExecutionState = json.loads(row["execution_json"])
        policy.update_execution(
            state,
            budget=budget,
            elapsed_seconds=elapsed_seconds,
            capabilities=capabilities,
            evaluation_skipped=evaluation_skipped,
            time_limit=time_limit,
        )
        db.execute(
            "UPDATE analysis_requests SET execution_json=? WHERE request_id=?",
            (_dumps(state), request_id),
        )


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


def save_evaluation(
    draft: DecisionResult, evaluations: list[Evaluation], *, db_path: str | Path | None = None
) -> None:
    draft = DecisionResult.model_validate(draft)
    evaluations = [Evaluation.model_validate(e) for e in evaluations]
    policy.validate_evaluations(
        evaluations, draft.request_id, "같은 요청의 평가자 네 명이 필요합니다."
    )
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        _require_running(db, draft.request_id)
        db.execute(
            "INSERT INTO evaluation_drafts VALUES (?,?,?)",
            (
                draft.request_id,
                draft.model_dump_json(
                    include={"request_id", "summary", "recommendations", "not_recommended"}
                ),
                _now(),
            ),
        )
        for evaluation in evaluations:
            db.execute(
                "INSERT INTO evaluations VALUES (?,?,?,?,?)",
                (
                    draft.request_id,
                    evaluation.evaluator,
                    evaluation.source,
                    evaluation.model_dump_json(),
                    _now(),
                ),
            )
        row = db.execute(
            "SELECT execution_json FROM analysis_requests WHERE request_id=?", (draft.request_id,)
        ).fetchone()
        state: ExecutionState = json.loads(row[0])
        state["evaluation_start_round"] = db.execute(
            "SELECT COALESCE(MAX(round),0) FROM specialist_consults WHERE request_id=?",
            (draft.request_id,),
        ).fetchone()[0]
        db.execute(
            "UPDATE analysis_requests SET execution_json=? WHERE request_id=?",
            (_dumps(state), draft.request_id),
        )


def save_evaluation_log(
    request_id: str, entries: list[EvaluationLogEntry], *, db_path: str | Path | None = None
) -> None:
    payload = [EvaluationLogEntry.model_validate(e).model_dump(mode="json") for e in entries]
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        _require_running(db, request_id)
        db.execute(
            "INSERT INTO evaluation_logs VALUES (?,?,?) ON CONFLICT(request_id) DO UPDATE "
            "SET log_json=excluded.log_json, updated_at=excluded.updated_at",
            (request_id, _dumps(payload), _now()),
        )


def get_evaluation(request_id: str, *, db_path: str | Path | None = None) -> dict | None:
    with connect(db_path) as db:
        draft = db.execute(
            "SELECT draft_json FROM evaluation_drafts WHERE request_id=?", (request_id,)
        ).fetchone()
        if draft is None:
            return None
        evaluations = [
            Evaluation.model_validate_json(row[0])
            for row in db.execute(
                "SELECT evaluation_json FROM evaluations WHERE request_id=?", (request_id,)
            )
        ]
        policy.validate_evaluations(evaluations, request_id, "저장된 평가 기록이 불완전합니다.")
        log = db.execute(
            "SELECT log_json FROM evaluation_logs WHERE request_id=?", (request_id,)
        ).fetchone()
        return {
            "draft": json.loads(draft[0]),
            "evaluations": sorted(evaluations, key=lambda e: EVALUATOR_IDS.index(e.evaluator)),
            "log": [EvaluationLogEntry.model_validate(e) for e in json.loads(log[0])]
            if log
            else [],
        }


def save_agent_brief(brief: AgentBrief, *, db_path: str | Path | None = None) -> None:
    brief = AgentBrief.model_validate(brief)
    with connect(db_path) as db:
        _require_running(db, brief.request_id, multi=True)
        db.execute(
            "INSERT INTO agent_briefs VALUES (?,?,?,?)",
            (brief.request_id, brief.agent_id, brief.model_dump_json(), _now()),
        )


# 저장 이력·복원 불변식을 직접 검사하는 테스트용 조회 경로를 유지합니다.
def list_agent_briefs(request_id: str, *, db_path: str | Path | None = None) -> list[AgentBrief]:
    with connect(db_path) as db:
        return [
            AgentBrief.model_validate_json(r[0])
            for r in db.execute(
                "SELECT brief_json FROM agent_briefs WHERE request_id=? ORDER BY agent_id",
                (_text(request_id),),
            )
        ]


def save_specialist_answer(answer: SpecialistAnswer, *, db_path: str | Path | None = None) -> None:
    answer = SpecialistAnswer.model_validate(answer)
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        _require_running(db, answer.request_id, multi=True)
        policy.validate_consult_count(
            db.execute(
                "SELECT count(*) FROM specialist_consults WHERE request_id=? AND round=?",
                (answer.request_id, answer.round),
            ).fetchone()[0]
        )
        db.execute(
            "INSERT INTO specialist_consults VALUES (?,?,?,?,?,?)",
            (
                answer.request_id,
                answer.round,
                answer.query.agent_id,
                answer.status,
                answer.model_dump_json(),
                _now(),
            ),
        )


# 저장 이력·복원 불변식을 직접 검사하는 테스트용 조회 경로를 유지합니다.
def list_specialist_answers(
    request_id: str, *, db_path: str | Path | None = None
) -> list[SpecialistAnswer]:
    with connect(db_path) as db:
        return [
            SpecialistAnswer.model_validate_json(r[0])
            for r in db.execute(
                "SELECT answer_json FROM specialist_consults WHERE request_id=? "
                "ORDER BY round,agent_id",
                (_text(request_id),),
            )
        ]


def _deliberation(db, request_id) -> DeliberationState:
    row = db.execute(
        "SELECT execution_json FROM analysis_requests WHERE request_id=?", (request_id,)
    ).fetchone()
    briefs = [
        AgentBrief.model_validate_json(r[0])
        for r in db.execute(
            "SELECT brief_json FROM agent_briefs WHERE request_id=? ORDER BY agent_id",
            (request_id,),
        )
    ]
    answers = [
        SpecialistAnswer.model_validate_json(r[0])
        for r in db.execute(
            "SELECT answer_json FROM specialist_consults WHERE request_id=? "
            "ORDER BY round,agent_id",
            (request_id,),
        )
    ]
    attempted = {}
    for saved in db.execute(
        "SELECT plan_json FROM map_observations WHERE request_id=? ORDER BY attempt", (request_id,)
    ):
        for query in MapLookupPlan.model_validate_json(saved[0]).unique_queries():
            attempted[(query.kind, query.industry_code, query.facility_code, query.query)] = query
    return {
        "briefs": briefs,
        "specialist_answers": answers,
        "map_queries": list(attempted.values()),
        "consult_round": max((a.round for a in answers), default=0),
        "map_attempt": db.execute(
            "SELECT MAX(attempt) FROM map_observations WHERE request_id=? AND adopted=1",
            (request_id,),
        ).fetchone()[0],
        "execution": json.loads(row[0]) if row else {},
    }


def get_deliberation(request_id: str, *, db_path: str | Path | None = None) -> DeliberationState:
    with connect(db_path) as db:
        return _deliberation(db, _text(request_id))


def append_event(
    request_id: str,
    stage: str,
    event: str,
    detail: dict[str, Any],
    *,
    db_path: str | Path | None = None,
) -> int:
    """진행 이벤트를 요청별 순번으로 추가합니다."""
    request_id = _text(request_id)
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        (seq,) = db.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM analysis_events WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        db.execute(
            "INSERT INTO analysis_events VALUES (?, ?, ?, ?, ?, ?)",
            (
                request_id,
                seq,
                _text(stage),
                event,
                _dumps(detail),
                _now(),
            ),
        )
    return seq


def list_events(
    request_id: str, *, after: int = 0, db_path: str | Path | None = None
) -> list[AnalysisEvent]:
    """after 다음 순번부터 진행 이벤트를 돌려줍니다."""
    with connect(db_path) as db:
        rows = db.execute(
            "SELECT seq, created_at, stage, event, detail_json FROM analysis_events "
            "WHERE request_id = ? AND seq > ? ORDER BY seq",
            (_text(request_id), after),
        ).fetchall()
    return [
        {
            "seq": row["seq"],
            "at": row["created_at"],
            "stage": row["stage"],
            "event": row["event"],
            "detail": json.loads(row["detail_json"]),
        }
        for row in rows
    ]


def fail_interrupted(*, db_path: str | Path | None = None) -> int:
    """서버가 멈춰 끊긴 실행 중 요청을 실패로 닫습니다. 서버 시작 때만 호출합니다."""
    error = AgentError(
        code="INTERRUPTED",
        message="서버가 다시 시작되어 분석이 중단되었습니다. 다시 요청해 주세요.",
    )
    with connect(db_path) as db:
        changed = db.execute(
            "UPDATE analysis_requests SET error_json = ?, status = 'failed', completed_at = ? "
            "WHERE status IN ('pending', 'running')",
            (error.model_dump_json(), _now()),
        )
    return changed.rowcount


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
