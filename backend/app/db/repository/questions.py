"""질문 대기·답변 선점과 재개 자료 복원입니다."""

import json
import sqlite3
from pathlib import Path

from app.db.connection import connect
from app.db.types import (
    ResumeBundle,
)
from app.industries.catalog import CATALOG_VERSION
from app.schemas import (
    AGENT_IDS,
    AgentAnalysis,
    AnalysisTask,
    AnswerSubmission,
    DecisionRequest,
    QuestionSnapshot,
    QuestionSnapshotV2,
    Site,
    normalize_answers,
)

from .common import AnswerConflictError, _analysis_row, _now, _request_row, _text
from .deliberation import _deliberation
from .map import _get_map_observation
from .results import _supplement_sources


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
        return _get_question_snapshot(db, request_id)


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


def _get_question_snapshot(db, request_id):
    row = db.execute(
        "SELECT snapshot_json FROM question_sessions WHERE request_id=?", (_text(request_id),)
    ).fetchone()
    return parse_snapshot(row[0]) if row else None
