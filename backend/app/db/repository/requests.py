"""요청 상태와 실패·재시도 저장입니다."""

import json
from pathlib import Path
from typing import Any

from app.db.connection import connect
from app.db.types import (
    DecisionFailure,
    ResumeBundle,
)
from app.industries.catalog import CATALOG_VERSION
from app.schemas import (
    AgentError,
    AnalysisMode,
    AnalysisTask,
    validate_radius,
)
from app.services import execution_policy as policy

from .common import DecisionRetryConflictError, _dumps, _now, _request_row, _require_changed, _text
from .deliberation import _deliberation
from .evaluations import _get_evaluation
from .map import _get_map_lookup
from .questions import _get_question_snapshot, _load_resume_context
from .results import _list_agent_results, _list_supplement_events


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
        return _list_decision_failures(db, request_id)


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


def _list_decision_failures(db, request_id):
    return [
        {"failed_at": row[0], "error": json.loads(row[1]), "diagnostics": json.loads(row[2])}
        for row in db.execute(
            "SELECT failed_at,error_json,diagnostics_json FROM decision_failures "
            "WHERE request_id=? ORDER BY failed_at",
            (_text(request_id),),
        )
    ]


def get_analysis_view_data(request_id: str, *, db_path: str | Path | None = None):
    """상세 화면에 필요한 저장 자료를 하나의 연결에서 읽습니다."""
    with connect(db_path) as db:
        row = _request_row(db, _text(request_id))
        if row is None:
            return None
        request = dict(row)
        execution = json.loads(request["execution_json"])
        return {
            "request": request,
            "evaluation": _get_evaluation(db, request_id)
            if execution.get("capabilities", {}).get("evaluators")
            else None,
            "deliberation": _deliberation(db, request_id)
            if request["analysis_mode"] == "multi_agent"
            else None,
            "questions": _get_question_snapshot(db, request_id),
            "map": _get_map_lookup(db, request_id),
            "decision_failures": _list_decision_failures(db, request_id),
            "analyses": _list_agent_results(db, request_id),
            "supplements": _list_supplement_events(db, request_id),
        }
