"""진행 이벤트 저장과 조회입니다."""

import json
from pathlib import Path
from typing import Any

from app.db.connection import connect
from app.db.types import (
    AnalysisEvent,
)

from .common import _dumps, _now, _request_row, _text


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
        return _list_events(db, request_id, after=after)


def _list_events(db, request_id, *, after=0):
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


def get_request_events(request_id: str, *, after: int = 0, db_path: str | Path | None = None):
    """요청 상태와 이벤트를 같은 연결에서 읽습니다."""
    with connect(db_path) as db:
        row = _request_row(db, _text(request_id))
        return (dict(row), _list_events(db, request_id, after=after)) if row else (None, [])
