"""DB 경로·연결·초기화를 관리합니다."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def resolve_path(db_path: str | Path | None = None) -> Path:
    value = db_path if db_path is not None else os.getenv("SQLITE_PATH", "storage/chaeum.sqlite3")
    if not str(value).strip() or str(value) == ":memory:":
        raise ValueError("영속 SQLite 파일 경로가 필요합니다.")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else BACKEND_DIR / path).resolve()


@contextmanager
def connect(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """초기화된 파일만 열고 트랜잭션 종료 후 연결을 닫습니다."""
    connection = sqlite3.connect(resolve_path(db_path).as_uri() + "?mode=rw", uri=True, timeout=5)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(db_path: str | Path | None = None) -> Path:
    """처음 실행할 때 파일과 테이블을 생성합니다. 기존 자료는 유지합니다."""
    path = resolve_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(files("app.db").joinpath("schema.sql").read_text(encoding="utf-8"))
    finally:
        connection.close()
    return path
