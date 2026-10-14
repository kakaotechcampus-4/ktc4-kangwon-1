"""단일 공개 API와 요청 DB 버전 경계를 검증합니다."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from app.db.connection import initialize
from app.main import create_app
from app.schemas import DecisionResult
from app.services.settings import ExecutionSettings


class PublicApiTests(unittest.TestCase):
    def test_old_database_is_rejected_without_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.sqlite3"
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

    def test_public_mock_question_resume_final_events(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = ExecutionSettings(db_path=Path(directory) / "new.sqlite3")
            with TestClient(create_app(settings=settings, load_env=False)) as client:
                response = client.post(
                    "/api/v1/analyses?mock=true", json={"address": "시험", "allow_questions": True}
                )
                self.assertEqual(response.status_code, 200, response.text)
                waiting = response.json()
                self.assertEqual(waiting["status"], "waiting_for_input")
                request_id = waiting["request_id"]
                response = client.post(
                    f"/api/v1/analyses/{request_id}/answers?mock=true",
                    json={
                        "question_session_id": waiting["question_session_id"],
                        "answers": {q["field"]: "시험 답변" for q in waiting["questions"]},
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                result = DecisionResult.model_validate(response.json())
                self.assertEqual(result.review_completeness, 1)
                detail = client.get(f"/api/v1/analyses/{request_id}").json()
                self.assertEqual(detail["status"], "completed")
                self.assertIn("rendered", detail)
                events = client.get(f"/api/v1/analyses/{request_id}/events").json()
                self.assertIn("evaluation", {e["stage"] for e in events["events"]})
