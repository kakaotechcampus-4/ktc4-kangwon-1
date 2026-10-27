"""단일 분석 요청의 상태와 위치를 저장합니다."""

from app.clock import utc_now_iso
from app.db.connection import connect
from app.industries.catalog import CATALOG_VERSION
from app.schemas import AgentError, AnalysisTask, validate_radius

from .common import _request_row, _require_changed, _text


def create_request(request_id, address, *, radius_m=None, db_path=None):
    request_id, address = _text(request_id), _text(address)
    if radius_m is not None:
        radius_m = validate_radius(radius_m)
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO analysis_requests(request_id,input_address,radius_m,catalog_version,"
            "status,created_at) VALUES(?,?,?,?,'pending',?)",
            (request_id, address, radius_m, CATALOG_VERSION, utc_now_iso()),
        )


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
