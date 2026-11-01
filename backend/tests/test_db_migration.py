"""요청 DB 스키마 버전 판정과 적용 순서를 검증합니다.

무중단 배포에서 새 버전을 올린 뒤 구 릴리스로 되돌아갈 수 있어야 하므로,
"나보다 새 버전"은 막지 않고 "나보다 옛 버전"만 조건부로 막습니다.
"""

import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from app.db import repository as repo
from app.db.connection import SCHEMA_VERSION, connect, initialize

# 인증 때문에 v6에서 늘어난 표입니다. 되돌릴 때 외래키 순서가 있어 역순으로 지웁니다.
AUTH_TABLES = (
    "analysis_owners",
    "login_attempts",
    "email_tokens",
    "oauth_states",
    "user_sessions",
    "user_identities",
    "users",
)


def _user_version(path: Path) -> int:
    with closing(sqlite3.connect(path)) as db:
        return int(db.execute("PRAGMA user_version").fetchone()[0])


def _set_user_version(path: Path, version: int) -> None:
    with closing(sqlite3.connect(path)) as db:
        db.execute(f"PRAGMA user_version = {version}")
        db.commit()


class SchemaVersionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def test_new_file_gets_current_version(self):
        path = self.directory / "new.sqlite3"
        initialize(path)
        self.assertEqual(_user_version(path), SCHEMA_VERSION)

    def test_reinitialize_keeps_existing_rows(self):
        path = self.directory / "again.sqlite3"
        initialize(path)
        repo.create_request("request", "주소", db_path=path)
        initialize(path)
        with connect(path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM analysis_requests").fetchone()[0], 1)

    def test_newer_version_is_accepted_so_rollback_stays_possible(self):
        # 더 새로운 코드가 올려 둔 파일. 여기서 막으면 구 릴리스로 되돌아갈 수 없습니다.
        path = self.directory / "future.sqlite3"
        initialize(path)
        repo.create_request("request", "주소", db_path=path)
        _set_user_version(path, SCHEMA_VERSION + 1)

        initialize(path)

        self.assertEqual(_user_version(path), SCHEMA_VERSION + 1)
        with connect(path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM analysis_requests").fetchone()[0], 1)

    def test_unknown_older_version_is_still_rejected(self):
        path = self.directory / "old.sqlite3"
        with closing(sqlite3.connect(path)) as db:
            db.execute("CREATE TABLE old_rows(value TEXT)")
            db.commit()

        with self.assertRaisesRegex(RuntimeError, "초기화"):
            initialize(path)

        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(
                db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),
                [("old_rows",)],
            )

    def test_allowed_older_version_is_upgraded_in_place(self):
        path = self.directory / "upgrade.sqlite3"
        initialize(path)
        repo.create_request("request", "주소", db_path=path)
        previous = SCHEMA_VERSION - 1
        _set_user_version(path, previous)

        with patch("app.db.connection._UPGRADABLE_FROM", frozenset({previous})):
            initialize(path)

        self.assertEqual(_user_version(path), SCHEMA_VERSION)
        with connect(path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM analysis_requests").fetchone()[0], 1)

    def test_version_is_not_bumped_when_schema_check_fails(self):
        # 버전을 먼저 쓰면 "표는 없는데 버전만 최신"인 파일이 남아 다음 기동에서
        # 검사를 통과해 버립니다. 적용 → 확인 → 버전 순서를 지키는지 봅니다.
        path = self.directory / "broken.sqlite3"
        with patch("app.db.connection._REQUIRED_TABLES", ("없는표",)):
            with self.assertRaisesRegex(RuntimeError, "없는표"):
                initialize(path)

        self.assertEqual(_user_version(path), 0)

    def test_auth_tables_are_added_to_a_version_five_database(self):
        """인증 표가 없던 v5 파일이 자료를 잃지 않고 올라가는지 봅니다.

        운영 DB가 이 경로를 그대로 탑니다. 표를 지우고 버전을 되돌려
        배포 직전의 파일 모양을 만든 뒤 다시 기동시킵니다.
        """
        path = self.directory / "v5.sqlite3"
        initialize(path)
        repo.create_request("before-auth", "주소", db_path=path)
        with closing(sqlite3.connect(path)) as db:
            for table in AUTH_TABLES:
                db.execute(f"DROP TABLE IF EXISTS {table}")
            db.execute("PRAGMA user_version = 5")
            db.commit()

        initialize(path)

        self.assertEqual(_user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            present = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        self.assertTrue(set(AUTH_TABLES) <= present)
        with connect(path) as db:
            self.assertEqual(
                db.execute(
                    "SELECT input_address FROM analysis_requests WHERE request_id=?",
                    ("before-auth",),
                ).fetchone()[0],
                "주소",
            )

    def test_concurrent_initialize_is_idempotent(self):
        path = self.directory / "concurrent.sqlite3"
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: initialize(path), range(4)))

        self.assertEqual(set(results), {path.resolve()})
        self.assertEqual(_user_version(path), SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
