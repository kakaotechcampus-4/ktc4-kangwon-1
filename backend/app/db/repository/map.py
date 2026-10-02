"""지도 조회와 관측 저장입니다."""

import sqlite3
from pathlib import Path

from app.db.connection import connect
from app.db.types import (
    MapLookupState,
)
from app.schemas import (
    AnalysisTask,
    MapLookupPlan,
    MapObservation,
    Site,
)
from app.services import execution_policy as policy

from .common import _now, _request_row, _text


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
        return _get_map_lookup(db, request_id)


def _get_map_lookup(db, request_id):
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
