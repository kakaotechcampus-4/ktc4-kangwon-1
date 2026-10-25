"""요청 DB 경로와 서버 동시성 설정을 검증합니다."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.settings import ExecutionSettings


class ExecutionSettingsTests(unittest.TestCase):
    def test_environment_sets_path_and_capacity(self):
        with patch.dict(
            os.environ,
            {"SQLITE_PATH": "storage/test.sqlite3", "ANALYSIS_MAX_CONCURRENCY": "3"},
            clear=True,
        ):
            settings = ExecutionSettings.from_env()
        self.assertEqual(
            settings.db_path, Path(__file__).resolve().parents[1] / "storage/test.sqlite3"
        )
        self.assertEqual(settings.max_concurrency, 3)

    def test_capacity_is_a_positive_integer(self):
        for value in (0, -1, True, 1.5, "2"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ExecutionSettings(max_concurrency=value)
        self.assertEqual(ExecutionSettings(max_concurrency=1).max_concurrency, 1)
