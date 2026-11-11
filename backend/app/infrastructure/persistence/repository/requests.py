"""단일 분석 요청의 상태와 위치를 저장합니다."""

from app.application.errors import INTERRUPTED_MESSAGE as INTERRUPTED_MESSAGE
from app.domain.industries.catalog import CATALOG_VERSION
from app.domain.schemas import AgentError, AnalysisTask, validate_radius
from app.infrastructure.persistence.connection import connect
from app.infrastructure.persistence.repository.common import _request_row, _require_changed, _text
from app.shared.clock import utc_now_iso


def create_request(request_id, address, *, radius_m=None, user_id=None, db_path=None):
    """요청과 소유자를 한 트랜잭션에 넣습니다.

    둘로 나누면 사이에서 죽었을 때 소유자 없는 요청이 생기고, 그런 요청은
    요청한 사람도 열 수 없게 됩니다.
    """
    request_id, address = _text(request_id), _text(address)
    if radius_m is not None:
        radius_m = validate_radius(radius_m)
    now = utc_now_iso()
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO analysis_requests(request_id,input_address,radius_m,catalog_version,"
            "status,created_at) VALUES(?,?,?,?,'pending',?)",
            (request_id, address, radius_m, CATALOG_VERSION, now),
        )
        if user_id is not None:
            db.execute(
                "INSERT INTO analysis_owners(request_id,user_id,created_at) VALUES(?,?,?)",
                (request_id, _text(user_id), now),
            )


def owner_of(request_id, *, db_path=None):
    """소유자 user_id. 소유자가 없거나 요청 자체가 없으면 None."""
    with connect(db_path) as db:
        row = db.execute(
            "SELECT user_id FROM analysis_owners WHERE request_id=?",
            (_text(request_id),),
        ).fetchone()
    return None if row is None else str(row["user_id"])


def list_user_requests(user_id, *, limit=20, offset=0, db_path=None):
    """내 분석 기록. 최신순이며 idx_analysis_owners_user 인덱스를 그대로 씁니다."""
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    with connect(db_path) as db:
        rows = db.execute(
            "SELECT r.request_id, r.input_address, r.status, r.created_at, r.completed_at"
            " FROM analysis_owners o JOIN analysis_requests r USING(request_id)"
            " WHERE o.user_id=? ORDER BY o.created_at DESC LIMIT ? OFFSET ?",
            (_text(user_id), limit, offset),
        ).fetchall()
        total = db.execute(
            "SELECT count(*) FROM analysis_owners WHERE user_id=?", (_text(user_id),)
        ).fetchone()[0]
    return [dict(row) for row in rows], int(total)


def mark_running(request_id, *, db_path=None):
    with connect(db_path) as db:
        changed = db.execute(
            "UPDATE analysis_requests SET status='running' WHERE request_id=? AND status='pending'",
            (_text(request_id),),
        )
        _require_changed(changed, "대기 중인 요청이 없습니다.")


def save_site(task, *, db_path=None):
    task = AnalysisTask.model_validate(task)
    with connect(db_path) as db:
        changed = db.execute(
            "UPDATE analysis_requests SET site_json=? WHERE request_id=? AND status='running'",
            (task.site.model_dump_json(), task.request_id),
        )
        _require_changed(changed)


def get_request(request_id, *, db_path=None):
    with connect(db_path) as db:
        row = _request_row(db, _text(request_id))
        return dict(row) if row else None


def fail_interrupted(*, db_path=None):
    error = AgentError(code="INTERRUPTED", message=INTERRUPTED_MESSAGE)
    with connect(db_path) as db:
        changed = db.execute(
            "UPDATE analysis_requests SET error_json=?,status='failed',completed_at=? "
            "WHERE status IN ('pending','running')",
            (error.model_dump_json(), utc_now_iso()),
        )
    return changed.rowcount


# 아직 끝나지 않은 요청만 결과로 닫을 수 있습니다. 서버가 다시 켜질 때 진행 중이던
# 요청을 실패로 닫는데(fail_interrupted), 조건이 없으면 뒤늦게 끝난 작업이 그 요청을
# 완료로 되살려 실패 이유와 완료 상태가 함께 남는 행이 생깁니다.
OPEN_STATUSES = ("pending", "running", "waiting_for_input")


def save_outcome(request_id, *, result_text=None, completed_at=None, db_path=None):
    """이미 닫힌 요청은 건드리지 않습니다. 바꾼 행 수를 돌려줍니다."""
    placeholders = ",".join("?" * len(OPEN_STATUSES))
    with connect(db_path) as db:
        if result_text is None:
            changed = db.execute(
                "UPDATE analysis_requests SET status='waiting_for_input' "
                f"WHERE request_id=? AND status IN ({placeholders})",
                (request_id, *OPEN_STATUSES),
            )
        else:
            changed = db.execute(
                "UPDATE analysis_requests SET "
                "status='completed',result_json=?,completed_at=? "
                f"WHERE request_id=? AND status IN ({placeholders})",
                (result_text, completed_at, request_id, *OPEN_STATUSES),
            )
    return changed.rowcount


def record_failure(request_id, *, error_text, diagnostics_text, failed_at, db_path=None):
    with connect(db_path) as db:
        placeholders = ",".join("?" * len(OPEN_STATUSES))
        changed = db.execute(
            "UPDATE analysis_requests SET error_json=?,status='failed',completed_at=? "
            f"WHERE request_id=? AND status IN ({placeholders})",
            (error_text, failed_at, request_id, *OPEN_STATUSES),
        )
        if changed.rowcount != 1:
            raise ValueError("종료할 수 있는 요청이 없습니다.")
        db.execute(
            "INSERT INTO decision_failures(request_id,failed_at,error_json,"
            "diagnostics_json) "
            "VALUES(?,?,?,?)",
            (request_id, failed_at, error_text, diagnostics_text),
        )
