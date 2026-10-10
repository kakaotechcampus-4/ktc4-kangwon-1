"""부하 측정도 실제 호출 없이 임시 자료만 사용합니다."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.measure_backend_load import measure


class LoadHarnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_execution_accounts_for_every_request(self):
        with TemporaryDirectory() as folder:
            result = await measure("execution", 10, Path(folder) / "load.sqlite3")
        self.assertEqual(result["submitted"], 10)
        self.assertEqual(sum(result["outcomes"].values()), 10)
        self.assertGreater(result["outcomes"]["rejected"], 0)
        self.assertGreater(result["fake_calls"]["model"], 0)
        self.assertEqual(result["external_calls"], 0)
        self.assertGreater(result["db_statements"], 0)

    async def test_events_include_running_and_completed(self):
        with TemporaryDirectory() as folder:
            result = await measure("events", 10, Path(folder) / "load.sqlite3")
        self.assertEqual(result["outcomes"]["completed"], 10)
        self.assertEqual(set(result["event_statuses"]), {"running", "completed"})
        self.assertEqual(result["fake_calls"]["model"], 0)

    async def test_existing_database_is_never_overwritten(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "existing.sqlite3"
            path.write_bytes(b"keep")
            with self.assertRaises(FileExistsError):
                await measure("events", 10, path)
            self.assertEqual(path.read_bytes(), b"keep")
