"""저장소 공통 조회·저장 헬퍼와 예외입니다."""

import json
import sqlite3
from typing import Any


def _text(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("비어 있지 않은 문자열이 필요합니다.")
    return value.strip()


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _request_row(db: sqlite3.Connection, request_id: str) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM analysis_requests WHERE request_id=?", (request_id,)
    ).fetchone()


def _require_changed(changed, message="실행 중인 요청이 없습니다.") -> None:
    if changed.rowcount != 1:
        raise ValueError(message)
