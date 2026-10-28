"""단일 분석 요청의 상태와 위치를 저장합니다."""

from app.clock import utc_now_iso
from app.db.connection import connect
from app.industries.catalog import CATALOG_VERSION
from app.schemas import AgentError, AnalysisTask, validate_radius

from .common import _request_row, _require_changed, _text


def create_request(request_id, address, *, radius_m=None, user_id=None, db_path=None):
    """요청과 소유자를 한 트랜잭션에 넣습니다.

    둘로 나누면 사이에서 죽었을 때 소유자 없는 요청이 생기고, 그런 요청은
    옛 요청과 구분되지 않아 조회가 열려 버립니다.
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


# 이 시각 이전에 만들어진 요청은 소유자 기록이 없습니다. 인증을 붙이기 전의 자료라
# 조회를 막지 않습니다. 경계를 두지 않으면 앞으로 소유자 기록이 빠진 요청까지
# 전부 공개돼 영구 구멍이 됩니다.
LEGACY_OWNER_CUTOFF = "2026-10-27T00:00:00+00:00"


def owner_of(request_id, *, db_path=None):
    """소유자 user_id. 소유자가 없는 옛 요청이면 "legacy", 요청 자체가 없으면 None."""
    with connect(db_path) as db:
        row = db.execute(
            "SELECT o.user_id AS user_id, r.created_at AS created_at"
            " FROM analysis_requests r LEFT JOIN analysis_owners o USING(request_id)"
            " WHERE r.request_id=?",
            (_text(request_id),),
        ).fetchone()
    if row is None:
        return None
    if row["user_id"] is not None:
        return str(row["user_id"])
    return "legacy" if str(row["created_at"]) < LEGACY_OWNER_CUTOFF else None


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
    error = AgentError(code="INTERRUPTED", message="서버가 다시 시작되어 분석이 중단되었습니다.")
    with connect(db_path) as db:
        changed = db.execute(
            "UPDATE analysis_requests SET error_json=?,status='failed',completed_at=? "
            "WHERE status IN ('pending','running')",
            (error.model_dump_json(), utc_now_iso()),
        )
    return changed.rowcount
