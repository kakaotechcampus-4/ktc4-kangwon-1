"""지도 저장의 원자성과 요청 일치를 검사합니다."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from test_map_mapping import plan, task

from app.agents.map_analysis.agent import failed_observation
from app.db import repository as repo
from app.db.connection import initialize


class MapRepositoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = initialize(Path(tmp.name) / "map.sqlite3")
        self.task = task()
        repo.create_request(
            self.task.request_id, self.task.site.input_address, radius_m=300, db_path=self.path
        )
        repo.mark_running(self.task.request_id, db_path=self.path)
        repo.save_site(self.task, db_path=self.path)

    def test_incomplete_duplicate_and_wrong_observation(self):
        repo.start_map_lookup(self.task, plan(), db_path=self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            repo.start_map_lookup(self.task, plan(), db_path=self.path)
        with self.assertRaises(ValueError):
            repo.get_map_observation(self.task.request_id, db_path=self.path)
        observed = failed_observation(self.task, plan(), "TIMEOUT")
        with self.assertRaises(ValueError):
            repo.complete_map_lookup(
                observed.model_copy(update={"radius_m": 500}), db_path=self.path
            )
        repo.complete_map_lookup(observed, db_path=self.path)
        initialize(self.path)
        self.assertEqual(
            repo.get_map_observation(self.task.request_id, db_path=self.path), observed
        )
        with self.assertRaises(ValueError):
            repo.complete_map_lookup(observed, db_path=self.path)
