"""질문 대기의 원자성과 기존 DB 보존을 검사합니다."""

import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from test_questions import question

from app.db import repository as repo
from app.db.connection import connect, initialize
from app.schemas import (
    AGENT_IDS,
    AgentAnalysis,
    AnalysisTask,
    AnswerSubmission,
    QuestionSnapshot,
    Scope,
    Site,
    SupplementEvent,
    SupplementRequest,
    WaitingForInput,
)


class QuestionRepositoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "test.sqlite3"
        initialize(self.path)
        self.task = AnalysisTask(
            request_id="r",
            site=Site(input_address="주소", road_address="도로", latitude=37.0, longitude=127.0),
            radius_m=300,
        )
        repo.create_request("r", "주소", radius_m=300, db_path=self.path)
        repo.mark_running("r", db_path=self.path)
        repo.save_site(self.task, db_path=self.path)
        for aid in AGENT_IDS:
            repo.save_agent(
                AgentAnalysis(
                    request_id="r",
                    agent_id=aid,
                    status="ok",
                    scope=Scope(area="시험", period="시험"),
                    data={"count": 1},
                ),
                db_path=self.path,
            )
        self.snapshot = QuestionSnapshot(
            task=self.task,
            waiting=WaitingForInput(
                request_id="r",
                question_set_id="q",
                questions=[question("floor"), question("exclusive_area")],
            ),
            source_attempts=dict.fromkeys(AGENT_IDS, 1),
            supplement_done=False,
            feedback=[],
        )

    def save(self):
        self.assertTrue(hasattr(repo, "save_question_snapshot"))
        repo.save_question_snapshot(self.snapshot, db_path=self.path)

    def test_waiting_and_concurrent_normalized_claim(self):
        self.save()
        self.assertEqual(repo.get_request("r", db_path=self.path)["status"], "waiting_for_input")
        submission = AnswerSubmission(request_id="r", question_set_id="q", answers=[])
        with ThreadPoolExecutor(2) as pool:
            results = list(
                pool.map(
                    lambda _: repo.claim_question_resume(submission, db_path=self.path), range(2)
                )
            )
        self.assertEqual(sum(results), 1)
        saved = repo.get_question_answers("r", db_path=self.path)
        self.assertEqual([a.status for a in saved.answers], ["skipped", "skipped"])
        reordered = saved.model_copy(update={"answers": list(reversed(saved.answers))})
        self.assertFalse(repo.claim_question_resume(reordered, db_path=self.path))
        changed = AnswerSubmission(
            request_id="r",
            question_set_id="q",
            answers=[dict(field="floor", status="answered", value="2층")],
        )
        with self.assertRaises(ValueError):
            repo.claim_question_resume(changed, db_path=self.path)

    def test_rejected_second_attempt_does_not_replace_selected_source(self):
        original = AgentAnalysis.model_validate_json(
            repo.list_agent_results("r", db_path=self.path)[0]["analysis_json"]
        )
        candidate = original.model_copy(update={"data": {"count": 999}})
        event = SupplementEvent(
            request_id="r",
            request=SupplementRequest(
                agent_id=candidate.agent_id,
                operation="test",
                decision_question="질문",
                missing_information="정보",
                why_needed="근거",
                expected_impact="검토",
            ),
            status="succeeded",
            message="미채택",
            adopted=False,
            analysis=candidate,
        )
        repo.save_supplement_event(event, db_path=self.path)
        self.snapshot.supplement_done = True
        self.save()
        restored = repo.load_question_analyses(
            repo.get_question_snapshot("r", db_path=self.path), db_path=self.path
        )
        self.assertEqual([a.data["count"] for a in restored], [1, 1, 1])

    def test_bad_reference_or_failed_transition_is_atomic(self):
        self.assertTrue(hasattr(repo, "save_question_snapshot"))
        for bad in (
            self.snapshot.model_copy(update={"source_attempts": dict.fromkeys(AGENT_IDS, 2)}),
            self.snapshot.model_copy(
                update={"task": self.task.model_copy(update={"radius_m": 700})}
            ),
        ):
            with self.assertRaises(ValueError):
                repo.save_question_snapshot(bad, db_path=self.path)
        self.assertIsNone(repo.get_question_snapshot("r", db_path=self.path))
        with connect(self.path) as db:
            db.execute(
                "CREATE TRIGGER reject_wait BEFORE UPDATE OF status ON analysis_requests "
                "WHEN NEW.status='waiting_for_input' BEGIN SELECT RAISE(ABORT, 'test'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            repo.save_question_snapshot(self.snapshot, db_path=self.path)
        self.assertIsNone(repo.get_question_snapshot("r", db_path=self.path))

    def test_legacy_migration_preserves_children_and_is_repeatable(self):
        legacy = self.path.parent / "legacy.sqlite3"
        schema = (Path(__file__).parents[1] / "app/db/schema.sql").read_text("utf-8")
        schema = schema.replace(", 'waiting_for_input'", "")
        schema = "\n".join(
            line for line in schema.splitlines() if not line.strip().startswith("radius_m INTEGER")
        )
        with closing(sqlite3.connect(legacy)) as db, db:
            db.executescript(schema)
            db.execute(
                "INSERT INTO analysis_requests(request_id,input_address,status,created_at) "
                "VALUES ('old','주소','running','now')"
            )
            source = dict(
                request_id="old",
                agent_id="commercial_area",
                status="ok",
                scope=dict(area="지역", period="기간"),
                data=dict(count=1),
                warnings=[],
            )
            db.execute(
                "INSERT INTO agent_results VALUES ('old','commercial_area',1,'ok',?,'now')",
                (json.dumps(source),),
            )
            db.execute("CREATE INDEX custom_address ON analysis_requests(input_address)")
        initialize(legacy)
        initialize(legacy)
        with connect(legacy) as db:
            db.execute(
                "UPDATE analysis_requests SET status='waiting_for_input' WHERE request_id='old'"
            )
            self.assertEqual(db.execute("SELECT count(*) FROM agent_results").fetchone()[0], 1)
            self.assertIsNone(db.execute("SELECT radius_m FROM analysis_requests").fetchone()[0])
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertIsNotNone(
                db.execute("SELECT name FROM sqlite_master WHERE name='custom_address'").fetchone()
            )

    def test_migration_integrity_failure_rolls_back_original_table(self):
        legacy = self.path.parent / "invalid.sqlite3"
        schema = (Path(__file__).parents[1] / "app/db/schema.sql").read_text("utf-8")
        with closing(sqlite3.connect(legacy)) as db, db:
            db.executescript(schema.replace(", 'waiting_for_input'", ""))
            db.execute(
                "INSERT INTO analysis_requests(request_id,input_address,status,created_at) "
                "VALUES ('old','주소','running','now')"
            )
            source = dict(request_id="orphan", agent_id="commercial_area", status="ok")
            db.execute(
                "INSERT INTO agent_results VALUES ('orphan','commercial_area',1,'ok',?,'now')",
                (json.dumps(source),),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            initialize(legacy)
        with closing(sqlite3.connect(legacy)) as db:
            definition = db.execute(
                "SELECT sql FROM sqlite_master WHERE name='analysis_requests'"
            ).fetchone()[0]
            self.assertNotIn("'waiting_for_input'", definition)
            self.assertEqual(db.execute("SELECT count(*) FROM agent_results").fetchone()[0], 1)
            self.assertEqual(
                db.execute("SELECT request_id FROM analysis_requests").fetchone()[0], "old"
            )
            self.assertIsNone(
                db.execute(
                    "SELECT name FROM sqlite_master WHERE name='analysis_requests_new'"
                ).fetchone()
            )
