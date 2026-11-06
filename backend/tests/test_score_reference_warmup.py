"""경쟁 참고 분포의 첫 계산이 한 번만 돌고 서버 시작 때 미리 준비되는지 확인합니다."""

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.local_data import score_reference
from app.local_data.score_reference import city_reference, warm_reference
from app.main import create_app
from app.services.settings import ExecutionSettings

VERSIONS = [
    {"source": "stores", "version_id": "s", "file_hash": "hs", "quarter": "20262"},
    {"source": "areas", "version_id": "a", "file_hash": "ha"},
]


class ReferenceBuildTests(unittest.TestCase):
    def test_concurrent_first_build_runs_once(self):
        def slow_build(*_):
            time.sleep(0.3)
            return [{"area": "a", "counts": {}}], []

        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(score_reference, "CACHE_DIR", Path(folder)),
            patch.object(score_reference, "_build_reference", side_effect=slow_build) as build,
        ):
            city_reference.cache_clear()
            threads = [
                threading.Thread(target=city_reference, args=("p", "s", "a", "h", "x"))
                for _ in range(3)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            city_reference.cache_clear()
            self.assertEqual(build.call_count, 1)
            self.assertEqual(len(list(Path(folder).glob("*.json"))), 1)

    def test_warm_reference_uses_request_arguments(self):
        adapter = SimpleNamespace(path=Path("market.sqlite3").resolve(), versions=VERSIONS)
        with (
            patch("app.local_data.adapter.LocalAdapter", return_value=adapter) as make,
            patch.object(score_reference, "city_reference") as build,
        ):
            self.assertTrue(warm_reference("given.sqlite3"))
        make.assert_called_once_with("given.sqlite3")
        build.assert_called_once_with(str(adapter.path), "s", "a", "hs", "ha")

    def test_warm_reference_skips_without_single_pair(self):
        adapter = SimpleNamespace(path=Path("market.sqlite3"), versions=VERSIONS[:1])
        with (
            patch("app.local_data.adapter.LocalAdapter", return_value=adapter),
            patch.object(score_reference, "city_reference") as build,
        ):
            self.assertFalse(warm_reference())
        build.assert_not_called()


class StartupWarmupTests(unittest.TestCase):
    def start(self, warm):
        done = threading.Event()
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("app.main.warm_reference", side_effect=lambda: done.set()) as warmed,
        ):
            settings = ExecutionSettings(
                db_path=Path(folder) / "requests.sqlite3", warm_reference=warm
            )
            with TestClient(create_app(settings=settings, load_env=False)) as client:
                self.assertEqual(client.get("/health").status_code, 200)
                done.wait(2)
            return warmed.call_count

    def test_startup_warms_reference_only_when_enabled(self):
        self.assertEqual(self.start(True), 1)
        self.assertEqual(self.start(False), 0)

    def test_environment_flag(self):
        with patch.dict(os.environ, {"WARM_SCORE_REFERENCE": "1"}, clear=True):
            self.assertTrue(ExecutionSettings.from_env().warm_reference)
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(ExecutionSettings.from_env().warm_reference)
        self.assertFalse(ExecutionSettings().warm_reference)


if __name__ == "__main__":
    unittest.main()
