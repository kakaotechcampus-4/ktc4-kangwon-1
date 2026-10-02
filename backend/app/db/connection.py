"""DB 경로·연결·초기화를 관리합니다."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from importlib.resources import files
from pathlib import Path
from threading import Lock

BACKEND_DIR = Path(__file__).resolve().parents[2]
# ponytail: 초기화 잠금은 프로세스 내부용입니다. 다중 워커는 시작 전 마이그레이션이 필요합니다.
_INITIALIZE_LOCK = Lock()


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
    with _INITIALIZE_LOCK:
        return _initialize(path)


def _initialize(path: Path) -> Path:
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
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(analysis_requests)")}
            if "catalog_version" not in columns:
                connection.execute("ALTER TABLE analysis_requests ADD COLUMN catalog_version TEXT")
        _migrate_deliberation(connection, schema)
        _migrate_evaluation_rounds(connection, schema)
    finally:
        connection.close()
    return path


def _migrate_evaluation_rounds(connection: sqlite3.Connection, schema: str) -> None:
    """기존 전문가 이력을 보존하며 평가 이후 네 라운드를 추가로 허용합니다."""
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        definition = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='specialist_consults'"
        ).fetchone()[0]
        if "BETWEEN 1 AND 2" not in definition:
            return
        create = next(
            s for s in schema.split(";") if "CREATE TABLE IF NOT EXISTS specialist_consults" in s
        )
        extras = connection.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name='specialist_consults' "
            "AND type IN ('index','trigger') AND sql IS NOT NULL"
        ).fetchall()
        connection.execute(
            create.replace("IF NOT EXISTS specialist_consults", "specialist_consults_new")
        )
        connection.execute("INSERT INTO specialist_consults_new SELECT * FROM specialist_consults")
        connection.execute("DROP TABLE specialist_consults")
        connection.execute("ALTER TABLE specialist_consults_new RENAME TO specialist_consults")
        for (sql,) in extras:
            connection.execute(sql)
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise sqlite3.IntegrityError("기존 전문가 이력의 외래키 검사가 실패했습니다.")


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
            # SQL의 주석·문자열·문장 순서는 SQLite 파서가 처리하게 합니다.
            with closing(sqlite3.connect(":memory:")) as template:
                template.executescript(schema)
                create = template.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='analysis_requests'"
                ).fetchone()[0]
            create = create.replace(
                "CREATE TABLE analysis_requests", "CREATE TABLE analysis_requests_new", 1
            )
            connection.execute(create)
            columns = ",".join(
                row[1] for row in connection.execute("PRAGMA table_info(analysis_requests)")
            )
            connection.execute(
                f"INSERT INTO analysis_requests_new ({columns}) "
                f"SELECT {columns} FROM analysis_requests"
            )
            connection.execute("DROP TABLE analysis_requests")
            connection.execute("ALTER TABLE analysis_requests_new RENAME TO analysis_requests")
            for (sql,) in extras:
                connection.execute(sql)
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise sqlite3.IntegrityError("기존 이력의 외래키 무결성 검사가 실패했습니다.")
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def _migrate_deliberation(connection: sqlite3.Connection, schema: str) -> None:
    """이전 요청은 기존 모드로 남기고 지도·보완 이력의 차수를 보존합니다."""
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        columns = {r[1] for r in connection.execute("PRAGMA table_info(analysis_requests)")}
        if "analysis_mode" not in columns:
            connection.execute(
                "ALTER TABLE analysis_requests ADD COLUMN analysis_mode TEXT NOT NULL "
                "DEFAULT 'single_decision' "
                "CHECK (analysis_mode IN ('single_decision','multi_agent'))"
            )
        if "execution_json" not in columns:
            connection.execute(
                "ALTER TABLE analysis_requests ADD COLUMN execution_json "
                "TEXT NOT NULL DEFAULT '{}' "
                "CHECK (json_valid(execution_json) AND json_type(execution_json)='object')"
            )
        columns = {r[1] for r in connection.execute("PRAGMA table_info(supplement_events)")}
        if "analysis_attempt" not in columns:
            connection.execute(
                "ALTER TABLE supplement_events ADD COLUMN analysis_attempt INTEGER "
                "CHECK (analysis_attempt IS NULL OR "
                "(typeof(analysis_attempt)='integer' AND analysis_attempt>=2))"
            )
            connection.execute(
                "UPDATE supplement_events SET analysis_attempt=2 "
                "WHERE json_type(event_json,'$.analysis')='object' AND EXISTS "
                "(SELECT 1 FROM agent_results a WHERE a.request_id=supplement_events.request_id "
                "AND a.agent_id=supplement_events.agent_id AND a.attempt=2 "
                "AND json(a.analysis_json)=json(json_extract(event_json,'$.analysis')))"
            )
        columns = {r[1] for r in connection.execute("PRAGMA table_info(map_observations)")}
        if "attempt" not in columns:
            definition = next(
                s for s in schema.split(";") if "CREATE TABLE IF NOT EXISTS map_observations" in s
            )
            connection.execute(
                definition.replace("IF NOT EXISTS map_observations", "map_observations_new")
            )
            connection.execute(
                "INSERT INTO map_observations_new "
                "(request_id,attempt,adopted,plan_json,task_json,status,"
                "observation_json,created_at,completed_at) "
                "SELECT request_id,1,CASE WHEN status='completed' THEN 1 ELSE 0 END,"
                "plan_json,task_json,status,observation_json,created_at,completed_at "
                "FROM map_observations"
            )
            connection.execute("DROP TABLE map_observations")
            connection.execute("ALTER TABLE map_observations_new RENAME TO map_observations")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS one_running_map ON map_observations(request_id) "
            "WHERE status='running'"
        )
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise sqlite3.IntegrityError("기존 이력의 외래키 무결성 검사가 실패했습니다.")
