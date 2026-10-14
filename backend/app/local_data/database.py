"""분기 자료의 비활성 적재·원자적 활성화·직전 release 보존입니다."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.canonical import file_sha256
from app.clock import utc_now_iso
from app.industries.catalog import INDUSTRIES
from app.seoul import previous_quarter

SOURCES = ("stores", "lifecycle", "floating", "resident", "worker", "areas", "seoul_boundary")


class DataValidationError(Exception):
    """활성 자료를 바꾸지 않고 적재를 거절합니다."""


def default_path() -> Path:
    return Path(os.getenv("LOCAL_DATA_DB_PATH") or Path.home() / ".chaeum/market_data.sqlite3")


class LocalDataDB:
    """동기 파일 작업 전용. 비동기 진입점은 반드시 to_thread로 호출합니다."""

    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS data_versions (
                    version_id TEXT PRIMARY KEY, source TEXT NOT NULL, quarter TEXT NOT NULL,
                    file_hash TEXT NOT NULL, row_count INTEGER NOT NULL,
                    loaded_at TEXT NOT NULL, state TEXT NOT NULL
                        CHECK(state IN ('staged','active','retired')),
                    mapping_version TEXT NOT NULL,
                    UNIQUE(source,quarter,file_hash,mapping_version));
                CREATE TABLE IF NOT EXISTS data_releases (
                    release_id INTEGER PRIMARY KEY AUTOINCREMENT, activated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS release_versions (
                    release_id INTEGER REFERENCES data_releases ON DELETE CASCADE,
                    version_id TEXT REFERENCES data_versions,
                    PRIMARY KEY(release_id,version_id));
                CREATE TABLE IF NOT EXISTS api_pages (
                    collection_key TEXT NOT NULL, start INTEGER NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY(collection_key,start));
                CREATE TABLE IF NOT EXISTS http_usage (
                    day TEXT PRIMARY KEY, count INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS source_fields (
                    version_id TEXT PRIMARY KEY REFERENCES data_versions ON DELETE CASCADE,
                    columns_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS district_counts (
                    version_id TEXT REFERENCES data_versions ON DELETE CASCADE,
                    district_code TEXT NOT NULL, industry_code TEXT NOT NULL,
                    count INTEGER NOT NULL,
                    PRIMARY KEY(version_id,district_code,industry_code));
            """)
            for source in SOURCES:
                con.executescript(f"""
                    CREATE TABLE IF NOT EXISTS {source} (
                        version_id TEXT REFERENCES data_versions ON DELETE CASCADE,
                        row_key TEXT NOT NULL, area_code TEXT, industry_code TEXT,
                        district_code TEXT, latitude REAL, longitude REAL,
                        payload TEXT NOT NULL, PRIMARY KEY(version_id,row_key));
                    CREATE INDEX IF NOT EXISTS ix_{source}_area
                        ON {source}(version_id,area_code,industry_code);
                    CREATE INDEX IF NOT EXISTS ix_{source}_coords
                        ON {source}(version_id,latitude,longitude);
                """)

    @contextmanager
    def connection(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA journal_mode=WAL")
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def stage(self, source: str, quarter: str, rows, file_hash: str) -> str:
        if source not in SOURCES:
            raise DataValidationError("알 수 없는 원천")
        if quarter:
            previous_quarter(quarter)
        mapping_hash = file_sha256(Path(__file__).parents[1] / "industries/catalog.py")
        with self.connection() as con:
            existing = con.execute(
                "SELECT version_id FROM data_versions WHERE source=? AND quarter=? "
                "AND file_hash=? AND mapping_version=?",
                (source, quarter, file_hash, mapping_hash),
            ).fetchone()
            if existing:
                return existing[0]
            version = "dv_" + uuid4().hex
            con.execute(
                "INSERT INTO data_versions VALUES(?,?,?,?,?,?,?,?)",
                (
                    version,
                    source,
                    quarter,
                    file_hash,
                    0,
                    utc_now_iso(),
                    "staged",
                    mapping_hash,
                ),
            )
            count = 0
            columns = None
            try:
                for row in rows:
                    if not row.get("row_key") or not isinstance(row.get("payload"), dict):
                        raise DataValidationError("필수 행 키/원문 결측")
                    if columns is None:
                        columns = sorted(row["payload"])
                        con.execute(
                            "INSERT INTO source_fields VALUES(?,?)",
                            (version, json.dumps(columns, ensure_ascii=False)),
                        )
                    if set(row["payload"]) != set(columns):
                        raise DataValidationError("같은 버전의 원문 필드 목록이 다릅니다.")
                    con.execute(
                        f"INSERT INTO {source} VALUES(?,?,?,?,?,?,?,?)",
                        (
                            version,
                            str(row["row_key"]),
                            row.get("area_code"),
                            row.get("industry_code"),
                            row.get("district_code"),
                            row.get("latitude"),
                            row.get("longitude"),
                            json.dumps(
                                [row["payload"][c] for c in columns],
                                ensure_ascii=False,
                                allow_nan=False,
                                separators=(",", ":"),
                            ),
                        ),
                    )
                    count += 1
            except sqlite3.IntegrityError as exc:
                raise DataValidationError("중복 자연 키") from exc
            if not count:
                raise DataValidationError("빈 원천은 활성화할 수 없습니다.")
            con.execute("UPDATE data_versions SET row_count=? WHERE version_id=?", (count, version))
            if source == "stores":
                con.execute(
                    "INSERT INTO district_counts SELECT version_id,district_code,industry_code,"
                    "COUNT(*) FROM stores WHERE version_id=? AND industry_code IS NOT NULL "
                    "GROUP BY version_id,district_code,industry_code",
                    (version,),
                )
                districts = [
                    r[0]
                    for r in con.execute(
                        "SELECT DISTINCT district_code FROM stores WHERE version_id=?", (version,)
                    )
                ]
                con.executemany(
                    "INSERT OR IGNORE INTO district_counts VALUES(?,?,?,0)",
                    [(version, district, code) for district in districts for code in INDUSTRIES],
                )
            return version

    def raw_row(self, source: str, version: str, key: str) -> dict | None:
        if source not in SOURCES:
            raise DataValidationError("알 수 없는 원천")
        with self.connection() as con:
            row = con.execute(
                f"SELECT payload,columns_json FROM {source} JOIN source_fields "
                "USING(version_id) WHERE version_id=? AND row_key=?",
                (version, key),
            ).fetchone()
            return dict(zip(json.loads(row[1]), json.loads(row[0]), strict=True)) if row else None

    def validate_seoul_stores(self, version: str) -> None:
        expected = {
            "11110",
            "11140",
            "11170",
            "11200",
            "11215",
            "11230",
            "11260",
            "11290",
            "11305",
            "11320",
            "11350",
            "11380",
            "11410",
            "11440",
            "11470",
            "11500",
            "11530",
            "11545",
            "11560",
            "11590",
            "11620",
            "11650",
            "11680",
            "11710",
            "11740",
        }
        with self.connection() as con:
            actual = {
                r[0]
                for r in con.execute(
                    "SELECT DISTINCT district_code FROM stores WHERE version_id=?", (version,)
                )
            }
        if actual != expected:
            raise DataValidationError("서울 전체 25개 구 코드가 일치하지 않습니다.")

    def active_versions(self) -> list[str]:
        with self.connection() as con:
            return [
                r[0]
                for r in con.execute(
                    "SELECT version_id FROM release_versions WHERE release_id="
                    "(SELECT MAX(release_id) FROM data_releases) ORDER BY version_id"
                )
            ]

    def version(self, version_id: str) -> dict | None:
        with self.connection() as con:
            row = con.execute(
                "SELECT * FROM data_versions WHERE version_id=?", (version_id,)
            ).fetchone()
            return dict(row) if row else None

    def release_count(self) -> int:
        with self.connection() as con:
            return con.execute("SELECT COUNT(*) FROM data_releases").fetchone()[0]

    def activate(self, versions: list[str]) -> None:
        try:
            self._activate(versions)
        except DataValidationError:
            self.clear_staged()
            raise

    def _activate(self, versions: list[str]) -> None:
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            selected = []
            for vid in versions:
                row = con.execute(
                    "SELECT * FROM data_versions WHERE version_id=?", (vid,)
                ).fetchone()
                if row is None:
                    raise DataValidationError("존재하지 않는 자료 버전")
                selected.append(dict(row))
            if not selected:
                raise DataValidationError("원천 묶음이 비었습니다.")
            groups: dict[str, list[dict]] = {}
            for row in selected:
                groups.setdefault(row["source"], []).append(row)
            if (set(SOURCES) - {"seoul_boundary"}) - groups.keys():
                raise DataValidationError("기본 6원천 묶음이 필요합니다.")
            for source, count in (("lifecycle", 12), ("floating", 5)):
                if len(groups[source]) != count:
                    raise DataValidationError(f"{source} 원천은 {count}분기가 필요합니다.")
            latest = {
                max(row["quarter"] for row in groups[source])
                for source in ("stores", "lifecycle", "floating", "resident", "worker")
            }
            if "" in latest or len(latest) != 1:
                raise DataValidationError("원천 간 최신 분기가 일치하지 않습니다.")
            for source, group in groups.items():
                quarters = sorted(r["quarter"] for r in group)
                if len(quarters) != len(set(quarters)):
                    raise DataValidationError("같은 원천·분기의 중복 버전")
                if source in ("lifecycle", "floating"):
                    for a, b in zip(quarters, quarters[1:], strict=False):
                        if previous_quarter(b) != a:
                            raise DataValidationError("분기 누락")
                for row in group:
                    old = con.execute(
                        "SELECT row_count FROM data_versions WHERE source=? AND state='active' "
                        "AND quarter<=? ORDER BY quarter DESC LIMIT 1",
                        (source, row["quarter"]),
                    ).fetchone()
                    if old and not 0.5 <= row["row_count"] / old[0] <= 1.5:
                        raise DataValidationError("직전 활성 버전 대비 행 수 50% 초과 변동")
            current = [
                r[0]
                for r in con.execute(
                    "SELECT version_id FROM release_versions WHERE release_id="
                    "(SELECT MAX(release_id) FROM data_releases)"
                )
            ]
            if set(current) == set(versions):
                self._delete_unused_staged(con)
                return
            release = con.execute(
                "INSERT INTO data_releases(activated_at) VALUES(?)",
                (utc_now_iso(),),
            ).lastrowid
            con.execute("UPDATE data_versions SET state='retired' WHERE state='active'")
            for vid in versions:
                con.execute("INSERT INTO release_versions VALUES(?,?)", (release, vid))
                con.execute("UPDATE data_versions SET state='active' WHERE version_id=?", (vid,))
            con.execute(
                "DELETE FROM release_versions WHERE release_id NOT IN "
                "(SELECT release_id FROM data_releases ORDER BY release_id DESC LIMIT 2)"
            )
            con.execute(
                "DELETE FROM data_releases WHERE release_id NOT IN "
                "(SELECT release_id FROM data_releases ORDER BY release_id DESC LIMIT 2)"
            )
            con.execute(
                "DELETE FROM data_versions WHERE state='retired' AND version_id NOT IN "
                "(SELECT version_id FROM release_versions)"
            )
            self._delete_unused_staged(con)

    @staticmethod
    def _delete_unused_staged(con: sqlite3.Connection) -> None:
        con.execute(
            "DELETE FROM data_versions WHERE state='staged' AND version_id NOT IN "
            "(SELECT version_id FROM release_versions)"
        )

    def clear_staged(self) -> None:
        """실패한 적재만 정리하며 release가 참조하는 버전은 보존합니다."""
        with self.connection() as con:
            self._delete_unused_staged(con)

    def page(self, key: str, start: int) -> dict | None:
        with self.connection() as con:
            row = con.execute(
                "SELECT body FROM api_pages WHERE collection_key=? AND start=?", (key, start)
            ).fetchone()
            if row is None:
                return None
            checkpoint = json.loads(row[0])
            collected_at = checkpoint.get("collected_at")
            if not collected_at or datetime.fromisoformat(collected_at) < datetime.now(
                UTC
            ) - timedelta(days=1):
                con.execute("DELETE FROM api_pages WHERE collection_key=?", (key,))
                return None
            return checkpoint["body"]

    def save_page(self, key: str, start: int, body: dict) -> None:
        with self.connection() as con:
            con.execute(
                "INSERT OR REPLACE INTO api_pages VALUES(?,?,?)",
                (
                    key,
                    start,
                    json.dumps(
                        {"collected_at": utc_now_iso(), "body": body},
                        ensure_ascii=False,
                    ),
                ),
            )

    def reserve_http(self, limit: int = 9500) -> None:
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            day = datetime.now(UTC).astimezone().date().isoformat()
            con.execute("INSERT OR IGNORE INTO http_usage VALUES(?,0)", (day,))
            count = con.execute("SELECT count FROM http_usage WHERE day=?", (day,)).fetchone()[0]
            if count >= limit:
                raise DataValidationError(
                    "일일 HTTP 예산 소진: 다음 날 같은 명령으로 이어 받으세요."
                )
            con.execute("UPDATE http_usage SET count=count+1 WHERE day=?", (day,))

    def clear_pages(self, keys: list[str]) -> None:
        with self.connection() as con:
            con.executemany("DELETE FROM api_pages WHERE collection_key=?", [(k,) for k in keys])
        with self.connection() as con:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def vacuum(self) -> tuple[int, int]:
        before = self.path.stat().st_size
        with self.connection() as con:
            con.execute("VACUUM")
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return before, self.path.stat().st_size
