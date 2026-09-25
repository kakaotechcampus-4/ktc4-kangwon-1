"""SQLite의 영속 저장·제약조건·원자성을 검사합니다."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import repository as repo
from app.db.connection import (
    BACKEND_DIR,
    SCHEMA_VERSION,
    SchemaVersionError,
    connect,
    initialize,
    resolve_path,
)
from app.schemas import AgentAnalysis, AnalysisTask, DecisionResult, Scope, Site


class RepositoryTests(unittest.TestCase):
    def test_schema_version_is_stamped_and_idempotent(self):
        initialize(self.path)
        with connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
        self.assertEqual(repo.get_request("request", db_path=self.path)["status"], "running")

    def test_version_mismatch_fails_without_touching_data(self):
        with connect(self.path) as db:
            db.execute("PRAGMA user_version = 0")
        with self.assertRaises(SchemaVersionError) as caught:
            initialize(self.path)
        self.assertIn(str(resolve_path(self.path)), str(caught.exception))
        with connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 0)
        self.assertEqual(repo.get_request("request", db_path=self.path)["status"], "running")

    def test_radius_constraint(self):
        repo.create_request("new", "주소", radius_m=300, db_path=self.path)
        self.assertEqual(repo.get_request("new", db_path=self.path)["radius_m"], 300)
        for value in (0, -1, 1.5, "invalid"):
            with self.subTest(value=value), self.assertRaises(sqlite3.IntegrityError):
                with connect(self.path) as db:
                    db.execute(
                        "UPDATE analysis_requests SET radius_m = ? WHERE request_id = 'new'",
                        (value,),
                    )

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "results.sqlite3"
        initialize(self.path)
        repo.create_request("request", " 원본 주소 ", db_path=self.path)
        repo.mark_running("request", db_path=self.path)
        self.source = AgentAnalysis(
            request_id="request",
            agent_id="floating_population",
            status="no_data",
            scope=Scope(area="시험 지역", period="시험 기간"),
        )

    def result(self):
        return DecisionResult(
            schema_version="1.0",
            agent_id="decision",
            request_id="request",
            address="원본 주소",
            status="no_data",
            summary="자료 없음",
            recommendations=[],
            not_recommended=[],
            limitations=["자료 없음"],
            source_analyses=[self.source],
        )

    def test_initialize_and_path_are_stable(self):
        with patch.dict("os.environ", {"SQLITE_PATH": "storage/test.sqlite3"}):
            self.assertEqual(resolve_path(), BACKEND_DIR / "storage" / "test.sqlite3")
        initialize(self.path)
        self.assertEqual(repo.get_request("request", db_path=self.path)["status"], "running")
        with connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(db.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
        missing = self.path.parent / "missing.sqlite3"
        with self.assertRaises(sqlite3.OperationalError), connect(missing):
            pass
        self.assertFalse(missing.exists())

    def test_round_trip_and_attempt_history(self):
        task = AnalysisTask(
            request_id="request",
            site=Site(
                input_address="원본 주소",
                road_address="시험 도로",
                detail_address="302호",
                latitude=0.0,
                longitude=0.0,
            ),
        )
        repo.save_site(task, db_path=self.path)
        repo.save_agent(self.source, attempt=2, db_path=self.path)
        repo.save_agent(self.source, db_path=self.path)
        result = self.result()
        repo.complete_request(result, db_path=self.path)
        row = repo.get_request("request", db_path=self.path)
        self.assertEqual(row["input_address"], " 원본 주소 ")
        self.assertEqual(Site.model_validate_json(row["site_json"]), task.site)
        self.assertEqual(DecisionResult.model_validate_json(row["result_json"]), result)
        self.assertEqual(row["status"], "completed")
        self.assertTrue(row["completed_at"].endswith("+00:00"))
        self.assertEqual(
            [r["attempt"] for r in repo.list_agent_results("request", db_path=self.path)], [1, 2]
        )
        self.assertIsNone(repo.get_request("missing", db_path=self.path))
        self.assertEqual(repo.list_agent_results("missing", db_path=self.path), [])

    def test_duplicates_and_foreign_keys(self):
        with self.assertRaises(sqlite3.IntegrityError):
            repo.create_request("request", "변경 주소", db_path=self.path)
        repo.save_agent(self.source, db_path=self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            repo.save_agent(self.source, db_path=self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            repo.save_agent(
                self.source.model_copy(update={"request_id": "missing"}), db_path=self.path
            )
        self.assertEqual(
            repo.get_request("request", db_path=self.path)["input_address"], " 원본 주소 "
        )

    def test_database_constraints_reject_invalid_values(self):
        for sql in (
            "UPDATE analysis_requests SET status='unknown'",
            "UPDATE analysis_requests SET site_json='not-json'",
            "UPDATE analysis_requests SET status='completed'",
        ):
            with (
                self.subTest(sql=sql),
                self.assertRaises(sqlite3.IntegrityError),
                connect(self.path) as db,
            ):
                db.execute(sql)
        source_json = self.source.model_dump_json()
        for attempt, status, payload in (
            (0, "no_data", source_json),
            (1, "wrong", source_json),
            (1, "no_data", "{}"),
            (1, "no_data", "bad-json"),
        ):
            with self.subTest(attempt=attempt, status=status, payload=payload):
                with self.assertRaises(sqlite3.IntegrityError), connect(self.path) as db:
                    db.execute(
                        "INSERT INTO agent_results VALUES (?, ?, ?, ?, ?, ?)",
                        ("request", "floating_population", attempt, status, payload, "now"),
                    )

    def test_completion_failure_rolls_back(self):
        repo.save_agent(self.source, db_path=self.path)
        with connect(self.path) as db:
            db.execute(
                "CREATE TRIGGER reject_completion BEFORE UPDATE ON analysis_requests "
                "WHEN NEW.status = 'completed' BEGIN SELECT RAISE(ABORT, 'test'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            repo.complete_request(self.result(), db_path=self.path)
        row = repo.get_request("request", db_path=self.path)
        self.assertEqual(row["status"], "running")
        self.assertIsNone(row["result_json"])
        self.assertIsNone(row["completed_at"])
        self.assertEqual(repo.list_decision_results("request", db_path=self.path), [])

    def test_decision_history_and_duplicate_rejection(self):
        repo.save_agent(self.source, attempt=2, db_path=self.path)
        result = self.result()
        repo.complete_request(result, source_attempts={"floating_population": 2}, db_path=self.path)
        history = repo.list_decision_results("request", db_path=self.path)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["attempt"], 1)
        self.assertEqual(json.loads(history[0]["source_attempts_json"]), {"floating_population": 2})
        self.assertEqual(DecisionResult.model_validate_json(history[0]["result_json"]), result)
        self.assertIsNone(history[0]["supplement_request_json"])
        with self.assertRaises(sqlite3.IntegrityError):
            repo.complete_request(
                result, source_attempts={"floating_population": 2}, db_path=self.path
            )
        self.assertEqual(len(repo.list_decision_results("request", db_path=self.path)), 1)

    def test_invalid_source_attempt_does_not_finish_request(self):
        repo.save_agent(self.source, db_path=self.path)
        for mapping in ({}, {"floating_population": 0}, {"floating_population": 2}):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                repo.complete_request(self.result(), source_attempts=mapping, db_path=self.path)
        self.assertEqual(repo.get_request("request", db_path=self.path)["status"], "running")
        self.assertEqual(repo.list_decision_results("request", db_path=self.path), [])

    def test_validation_precedes_storage(self):
        with self.assertRaises(ValueError):
            repo.save_agent(self.source.model_copy(update={"status": "ok"}), db_path=self.path)
        wrong = self.result().model_copy(
            update={
                "source_analyses": [
                    self.source.model_copy(update={"request_id": "other"}),
                ]
            }
        )
        with self.assertRaises(ValueError):
            repo.complete_request(wrong, db_path=self.path)
        self.assertEqual(repo.list_agent_results("request", db_path=self.path), [])
