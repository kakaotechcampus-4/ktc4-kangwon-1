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
        schema = files("app.db").joinpath("schema.sql").read_text(encoding="utf-8")
        connection.executescript(schema)
        # 기존 요청의 반경은 알 수 없으므로 NULL로 보존합니다.
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(analysis_requests)")}
            if "radius_m" not in columns:
                connection.execute(
                    "ALTER TABLE analysis_requests ADD COLUMN radius_m INTEGER "
                    "CHECK (radius_m IS NULL OR (typeof(radius_m) = 'integer' AND radius_m > 0))"
                )
        _migrate_waiting(connection, schema)
    finally:
        connection.close()
    return path


def _migrate_waiting(connection: sqlite3.Connection, schema: str) -> None:
    """기존 부모 테이블의 상태 제약만 확장하고 자식 이력을 보존합니다."""
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            definition = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='analysis_requests'"
            ).fetchone()[0]
            if "'waiting_for_input'" in definition:
                return
            extras = connection.execute(
                "SELECT sql FROM sqlite_master WHERE tbl_name='analysis_requests' "
                "AND type IN ('index','trigger') AND sql IS NOT NULL"
            ).fetchall()
            create = schema.split(";", 1)[0].replace(
                "CREATE TABLE IF NOT EXISTS analysis_requests", "CREATE TABLE analysis_requests_new"
            )
            connection.execute(create)
            connection.execute(
                "INSERT INTO analysis_requests_new "
                "(request_id,input_address,radius_m,site_json,status,result_json,error_json,"
                "created_at,completed_at) "
                "SELECT request_id,input_address,radius_m,site_json,status,result_json,error_json,"
                "created_at,completed_at "
                "FROM analysis_requests"
            )
            connection.execute("DROP TABLE analysis_requests")
            connection.execute("ALTER TABLE analysis_requests_new RENAME TO analysis_requests")
            for (sql,) in extras:
                connection.execute(sql)
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise sqlite3.IntegrityError("기존 이력의 외래키 무결성 검사가 실패했습니다.")
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
