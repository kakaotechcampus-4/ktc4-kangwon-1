"""요청 ID·DB 초기화·기존 자료 보존을 검증합니다."""

import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app.db import repository as repo
from app.db.connection import BACKEND_DIR, connect, initialize, resolve_path
from app.schemas import AnalysisTask, Site


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "requests.sqlite3"
        initialize(self.path)
        repo.create_request(" request ", " 주소 ", db_path=self.path)

    def test_ids_and_events_are_normalized(self):
        repo.mark_running(" request ", db_path=self.path)
        repo.save_site(
            AnalysisTask(
                request_id="request",
                site=Site(
                    input_address="주소", road_address="주소", latitude=37.5, longitude=127.0
                ),
            ),
            db_path=self.path,
        )
        self.assertEqual(
            repo.append_event(" request ", "test", "started", {}, db_path=self.path), 1
        )
        row, events = repo.get_request_events(" request ", after=0, db_path=self.path)
        self.assertEqual(row["request_id"], "request")
        self.assertEqual(row["status"], "running")
        self.assertEqual([event["seq"] for event in events], [1])
        self.assertEqual(repo.get_request_events("request", after=1, db_path=self.path)[1], [])

    def test_parallel_initialization_preserves_existing_data(self):
        path = self.path.parent / "parallel.sqlite3"
        barrier = threading.Barrier(8)

        def start():
            barrier.wait(timeout=5)
            return initialize(path)

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(start) for _ in range(8)]
            self.assertEqual([future.result(timeout=15) for future in futures], [path] * 8)
        repo.create_request("preserved", "시험", db_path=path)
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(start) for _ in range(8)]
            for future in futures:
                future.result(timeout=15)
        self.assertEqual(repo.get_request("preserved", db_path=path)["status"], "pending")
        with connect(path) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_path_and_connection_settings_are_stable(self):
        with patch.dict("os.environ", {"SQLITE_PATH": "storage/test.sqlite3"}):
            self.assertEqual(resolve_path(), BACKEND_DIR / "storage/test.sqlite3")
        initialize(self.path)
        with connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        missing = self.path.parent / "missing.sqlite3"
        with self.assertRaises(sqlite3.OperationalError), connect(missing):
            pass
        self.assertFalse(missing.exists())
