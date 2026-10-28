"""DB 경로·연결·초기화를 관리합니다."""

import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
# ponytail: 초기화 잠금은 프로세스 내부용입니다. 다중 워커는 시작 전 마이그레이션이 필요합니다.
_INITIALIZE_LOCK = Lock()
SCHEMA_VERSION = 5
SQLITE_BUSY_TIMEOUT_MS = 30000

# 이 코드가 올려 줄 수 있는 옛 스키마 버전입니다.
# schema.sql 이 전부 `IF NOT EXISTS` 라, 테이블·인덱스를 "추가만" 하는 변경이면
# 스키마를 다시 실행하는 것만으로 올라갑니다. 기존 테이블의 칼럼이나 제약을
# 바꾸는 변경을 하려면 여기 더하지 말고 따로 이전 절차를 만드세요.
_UPGRADABLE_FROM: frozenset[int] = frozenset()

# 스키마가 실제로 적용됐는지 확인할 때 보는 표입니다. 하나라도 없으면 중단합니다.
_REQUIRED_TABLES = ("analysis_requests", "analysis_events", "snapshots", "facts")


def resolve_path(db_path: str | Path | None = None) -> Path:
    value = db_path if db_path is not None else os.getenv("SQLITE_PATH", "storage/chaeum.sqlite3")
    if not str(value).strip() or str(value) == ":memory:":
        raise ValueError("영속 SQLite 파일 경로가 필요합니다.")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else BACKEND_DIR / path).resolve()


@contextmanager
def connect(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """초기화된 파일만 열고 트랜잭션 종료 후 연결을 닫습니다."""
    connection = sqlite3.connect(
        resolve_path(db_path).as_uri() + "?mode=rw", uri=True, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000
    )
    try:
        connection.row_factory = sqlite3.Row
        connection.create_function("raw_request_id", 0, lambda: None)
        connection.create_function("raw_snapshot_id", 0, lambda: None)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        with connection:
            yield connection
    finally:
        connection.close()


@contextmanager
def readonly(path: str | Path, *, timeout: float = 5) -> Iterator[sqlite3.Connection]:
    """기존 파일을 읽기 전용으로 열고 연결을 반드시 닫습니다."""
    connection = sqlite3.connect(
        Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=timeout
    )
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


def _state(connection: sqlite3.Connection) -> tuple[int, bool]:
    """쓰기 잠금을 먼저 잡고 버전을 읽습니다.

    다른 프로세스가 같은 파일을 올리는 중일 수 있어, 잠금을 잡은 뒤에 읽어야
    남이 막 올려 둔 버전을 보게 됩니다. 무중단 배포에서 새 포트와 옛 포트가
    잠깐 겹치는 구간이 실제로 있습니다.
    """
    connection.execute("BEGIN IMMEDIATE")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    populated = (
        connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone()
        is not None
    )
    connection.commit()
    return version, populated


def _apply_schema(connection: sqlite3.Connection, path: Path) -> None:
    """스키마를 먼저 적용하고, 성공을 확인한 뒤에야 버전을 올립니다.

    순서가 중요합니다. executescript() 는 대기 중인 트랜잭션을 먼저 커밋하므로,
    버전을 앞서 쓰면 DDL 이 실패했을 때 "테이블은 없는데 버전만 최신"인 파일이
    남습니다. 그런 파일은 다음 기동 때 검사를 통과해 버려 더 찾기 어렵습니다.
    """
    schema = files("app.db").joinpath("schema.sql").read_text(encoding="utf-8")
    connection.executescript(schema)
    missing = [name for name in _REQUIRED_TABLES if not _has_table(connection, name)]
    if missing:
        raise RuntimeError(
            f"스키마를 적용했지만 {', '.join(missing)} 표가 없습니다. "
            f"{path.name} 을 확인하세요. 버전은 올리지 않았습니다."
        )
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    connection.commit()


def _has_table(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _initialize(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA journal_mode = WAL")
        version, populated = _state(connection)
        if populated and version > SCHEMA_VERSION:
            # 더 새로운 코드가 이미 올려 둔 파일입니다. 추가만 하는 변경이라는
            # 규칙 아래에서는 옛 코드도 그대로 읽을 수 있으므로 막지 않습니다.
            # 이걸 막으면 새 버전을 배포한 뒤 구 릴리스로 되돌아갈 길이 사라집니다.
            logger.warning(
                "요청 DB 스키마 버전 %s는 이 코드(%s)보다 새 버전입니다. 그대로 사용합니다.",
                version,
                SCHEMA_VERSION,
            )
            return path
        if populated and version < SCHEMA_VERSION and version not in _UPGRADABLE_FROM:
            raise RuntimeError(
                f"요청 DB 스키마 버전 {version}은 지원하지 않습니다. 서버를 중지하고 "
                f"{path.name} 및 -wal/-shm 파일을 백업·이동한 뒤 재시작하여 초기화하세요. "
                "LOCAL_DATA_DB_PATH의 자료 DB는 삭제하지 마세요."
            )
        if populated and version < SCHEMA_VERSION:
            logger.info("요청 DB 스키마를 %s에서 %s로 올립니다.", version, SCHEMA_VERSION)
        _apply_schema(connection, path)
    finally:
        connection.close()
    return path
