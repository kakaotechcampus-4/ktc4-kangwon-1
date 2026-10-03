"""멀티 실행의 이력·예산·재개 참조를 검사합니다."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from test_map_mapping import plan
from test_questions import question

from app.agents.map_analysis.agent import failed_observation
from app.db import repository as repo
from app.db.connection import connect, initialize
from app.mocks import mock_site
from app.schemas import (
    AGENT_IDS,
    AgentAnalysis,
    AgentBrief,
    AnalysisTask,
    QuestionSnapshotV2,
    SpecialistAnswer,
    SpecialistQuery,
    SupplementEvent,
    SupplementRequest,
    WaitingForInput,
)


class DeliberationRepositoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = initialize(Path(tmp.name) / "history.sqlite3")
        self.assertIn(
            "analysis_mode", __import__("inspect").signature(repo.create_request).parameters
        )
        repo.create_request(
            "r", "주소", radius_m=300, analysis_mode="multi_agent", db_path=self.path
        )
        repo.mark_running("r", db_path=self.path)
        self.task = AnalysisTask(request_id="r", site=mock_site("주소"), radius_m=300)
        repo.save_site(self.task, db_path=self.path)
        self.sources = []
        for aid in AGENT_IDS:
            source = AgentAnalysis(
                request_id="r",
                agent_id=aid,
                status="ok",
                scope={"area": "시험", "period": "시험"},
                data={"count": 1},
            )
            repo.save_agent(source, db_path=self.path)
            self.sources.append(source)
            repo.save_agent_brief(
                AgentBrief(
                    request_id="r", agent_id=aid, source="fallback", headline="원자료", findings=[]
                ),
                db_path=self.path,
            )

    def test_history_duplicates_and_monotonic_budget(self):
        briefs = repo.list_agent_briefs("r", db_path=self.path)
        self.assertEqual(len(briefs), 3)
        with self.assertRaises(sqlite3.IntegrityError):
            repo.save_agent_brief(briefs[0], db_path=self.path)
        answer = SpecialistAnswer(
            request_id="r",
            round=1,
            query=SpecialistQuery(
                agent_id="floating_population",
                question="질문",
                why_needed="이유",
                expected_impact="영향",
            ),
            status="unavailable",
            findings=[],
            limitations=["자료 없음"],
        )
        repo.save_specialist_answer(answer, db_path=self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            repo.save_specialist_answer(answer, db_path=self.path)
        repo.update_execution_state(
            "r", budget={"used": 10, "calls": []}, elapsed_seconds=30, db_path=self.path
        )
        with self.assertRaises(ValueError):
            repo.update_execution_state("r", budget={"used": 9, "calls": []}, db_path=self.path)
        self.assertEqual(repo.list_specialist_answers("r", db_path=self.path), [answer])
        self.assertEqual(
            json.loads(repo.get_request("r", db_path=self.path)["execution_json"])["budget"][
                "used"
            ],
            10,
        )

    def test_supplements_allocate_attempts_and_preserve_adopted_source(self):
        source = self.sources[0]
        request = SupplementRequest(
            agent_id=source.agent_id,
            operation="test",
            decision_question="질문",
            missing_information="정보",
            why_needed="이유",
            expected_impact="영향",
        )
        for adopted, count, expected in ((True, 2, 2), (False, 99, 3)):
            event = SupplementEvent(
                request_id="r",
                request=request,
                status="succeeded",
                adopted=adopted,
                message="완료",
                analysis=source.model_copy(update={"data": {"count": count}}),
            )
            self.assertEqual(repo.save_supplement_event(event, db_path=self.path), expected)
        bundle = repo.load_resume_context("r", db_path=self.path)
        self.assertEqual(bundle["source_attempts"][source.agent_id], 2)
        self.assertEqual(bundle["request"].analyses[0].data["count"], 2)

    def test_map_history_keeps_previous_adoption(self):
        observed = failed_observation(self.task, plan(), "TEST")
        self.assertEqual(repo.start_map_lookup(self.task, plan(), db_path=self.path), 1)
        repo.complete_map_lookup(observed, db_path=self.path)
        next_plan = plan()
        next_plan.queries.append(next_plan.queries[0].model_copy(update={"query": "다른 카페"}))
        self.assertEqual(repo.start_map_lookup(self.task, next_plan, db_path=self.path), 2)
        second = failed_observation(self.task, next_plan, "SECOND")
        repo.complete_map_lookup(second, adopted=False, db_path=self.path)
        initialize(self.path)
        self.assertEqual(repo.get_map_observation("r", db_path=self.path), observed)
        attempted = repo.load_resume_context("r", db_path=self.path)["map_queries"]
        self.assertEqual(attempted, next_plan.queries)
        with connect(self.path) as db:
            self.assertEqual(
                [
                    tuple(r)
                    for r in db.execute(
                        "SELECT attempt,adopted FROM map_observations ORDER BY attempt"
                    )
                ],
                [(1, 1), (2, 0)],
            )

    def test_v2_snapshot_checks_budget_and_brief_references(self):
        snapshot = QuestionSnapshotV2(
            task=self.task,
            waiting=WaitingForInput(
                request_id="r", question_set_id="q", questions=[question("floor")]
            ),
            source_attempts=dict.fromkeys(AGENT_IDS, 1),
            supplement_done=False,
            feedback=[],
            brief_agents=list(AGENT_IDS),
        )
        with self.assertRaises(ValueError):
            repo.save_question_snapshot(
                snapshot.model_copy(update={"llm_calls": 1}), db_path=self.path
            )
        repo.save_question_snapshot(snapshot, db_path=self.path)
        self.assertIsInstance(
            repo.get_question_snapshot("r", db_path=self.path), QuestionSnapshotV2
        )

    def test_legacy_map_and_request_migration_preserves_existing_rows(self):
        path = self.path.parent / "legacy.sqlite3"
        schema = (Path(__file__).parents[1] / "app/db/schema.sql").read_text("utf-8")
        old = "\n".join(
            line
            for line in schema.splitlines()
            if not line.strip().startswith(
                ("analysis_mode TEXT", "execution_json TEXT", "analysis_attempt INTEGER")
            )
        )
        current_map = next(
            s for s in old.split(";") if "CREATE TABLE IF NOT EXISTS map_observations" in s
        )
        legacy_map = "\n".join(
            line
            for line in current_map.splitlines()
            if not line.strip().startswith(("attempt INTEGER", "adopted INTEGER", "PRIMARY KEY"))
        )
        legacy_map = legacy_map.replace(
            "request_id TEXT NOT NULL", "request_id TEXT PRIMARY KEY NOT NULL"
        )
        old = old.replace(current_map, legacy_map)
        observed = failed_observation(self.task, plan(), "TEST")
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript(old)
            db.execute(
                "INSERT INTO analysis_requests(request_id,input_address,status,created_at) "
                "VALUES ('r','주소','running','now')"
            )
            db.execute(
                "INSERT INTO map_observations VALUES (?,?,?,?,?,?,?)",
                (
                    "r",
                    plan().model_dump_json(),
                    self.task.model_dump_json(),
                    "completed",
                    observed.model_dump_json(),
                    "now",
                    "now",
                ),
            )
        initialize(path)
        initialize(path)
        self.assertEqual(repo.get_request("r", db_path=path)["analysis_mode"], "single_decision")
        self.assertEqual(repo.get_map_observation("r", db_path=path), observed)
        with connect(path) as db:
            self.assertEqual(
                tuple(db.execute("SELECT attempt,adopted FROM map_observations").fetchone()), (1, 1)
            )
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
