"""DB 경로·연결·초기화를 관리합니다."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from threading import Lock

BACKEND_DIR = Path(__file__).resolve().parents[2]
# ponytail: 초기화 잠금은 프로세스 내부용입니다. 다중 워커는 시작 전 마이그레이션이 필요합니다.
_INITIALIZE_LOCK = Lock()
SCHEMA_VERSION = 3


def resolve_path(db_path: str | Path | None = None) -> Path:
    value = db_path if db_path is not None else os.getenv("SQLITE_PATH", "storage/chaeum.sqlite3")
    if not str(value).strip() or str(value) == ":memory:":
        raise ValueError("영속 SQLite 파일 경로가 필요합니다.")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else BACKEND_DIR / path).resolve()


@contextmanager
def connect(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """초기화된 파일만 열고 트랜잭션 종료 후 연결을 닫습니다."""
    connection = sqlite3.connect(resolve_path(db_path).as_uri() + "?mode=rw", uri=True, timeout=30)
    try:
        connection.row_factory = sqlite3.Row
        connection.create_function("raw_request_id", 0, lambda: None)
        connection.create_function("raw_snapshot_id", 0, lambda: None)
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            yield connection
    finally:
        connection.close()


@contextmanager
def readonly(path: str | Path, *, timeout: float = 5) -> Iterator[sqlite3.Connection]:
    """기존 파일을 읽기 전용으로 열고 연결을 반드시 닫습니다."""
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=timeout)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def initialize(db_path: str | Path | None = None) -> Path:
    """처음 실행할 때 파일과 테이블을 생성합니다. 기존 자료는 유지합니다."""
    path = resolve_path(db_path)
    with _INITIALIZE_LOCK:
        return _initialize(path)


def _initialize(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        populated = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1"
        ).fetchone()
        if populated and version != SCHEMA_VERSION:
            raise RuntimeError(
                f"요청 DB 스키마 버전 {version}은 지원하지 않습니다. 서버를 중지하고 "
                f"{path.name} 및 -wal/-shm 파일을 백업·이동한 뒤 재시작하여 초기화하세요. "
                "LOCAL_DATA_DB_PATH의 자료 DB는 삭제하지 마세요."
            )
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        schema = files("app.db").joinpath("schema.sql").read_text(encoding="utf-8")
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.executescript(schema)
    finally:
        connection.close()
    return path
