"""남은 불변 저장·조회 계획·비교 반경·질문 트랜잭션 회귀입니다."""

import asyncio
import json
import sqlite3
import tempfile
import unittest
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import get_args
from unittest.mock import MagicMock, patch

from app.agents.agentic.contracts import Metric
from app.agents.agentic.facts import register_fact
from app.agents.agentic.scoring import WEIGHTS, evaluate, result, summarize
from app.agents.agentic.snapshot import persist_report
from app.db.connection import connect, initialize
from app.db.repository import create_request
from app.errors import AnalysisConflictError
from app.local_data.adapter import LocalAdapter
from app.local_data.boundary import boundary_limitations
from app.schemas import AnalysisTask, Site
from app.storage.raw import CaptureScope, capture_scope


class RemainingStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = initialize(Path(self.temp.name) / "requests.sqlite3")
        create_request("one", "시험", db_path=self.path)
        self.manager = capture_scope("one", self.path)
        self.scope = await self.manager.__aenter__()
        await self.scope.record(
            source="commercial_area",
            source_type="api",
            args={},
            page="1",
            status=200,
            payload={"rows": [{"value": 7}]},
        )
        with connect(self.path) as db:
            self.raw_id = db.execute("SELECT raw_row_id FROM raw_rows").fetchone()[0]
        self.fact_id = register_fact(
            self.scope,
            industry_code=None,
            source="commercial_area",
            metric="store_count",
            value=7,
            unit="개",
            status="observed",
            row_ids=[self.raw_id],
        )
        row = summarize("I201", {item: result(item) for item in WEIGHTS}, "unknown")
        self.score_id = persist_report(self.scope, {"rows": [row], "top5": [row]}, {}, [])
        with connect(self.path) as db:
            db.execute(
                "INSERT INTO local_provenance "
                "VALUES('provenance',?,'commercial_area','[]','{}','test')",
                (self.scope.snapshot_id,),
            )
            db.execute(
                "INSERT INTO local_fact_lineage VALUES(?,'provenance','row','column')",
                (self.fact_id,),
            )

    async def asyncTearDown(self):
        await self.manager.__aexit__(None, None, None)
        self.temp.cleanup()

    async def test_fact_sources_scores_and_lineage_are_immutable(self):
        targets = [
            ("facts", "fact_id", self.fact_id, "unit"),
            ("fact_sources", "fact_id", self.fact_id, "field_pointer"),
            ("scores", "score_snapshot_id", self.score_id, "fact_ids_json"),
            ("local_fact_lineage", "fact_id", self.fact_id, "column_name"),
        ]
        for table, key, value, column in targets:
            for sql in [
                f"UPDATE {table} SET {column}={column} WHERE {key}=?",
                f"DELETE FROM {table} WHERE {key}=?",
            ]:
                with (
                    self.subTest(sql=sql),
                    self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"),
                    connect(self.path) as db,
                ):
                    db.execute(sql, (value,))

    async def test_metric_item_and_run_status_checks(self):
        for metric in get_args(Metric):
            register_fact(
                self.scope,
                industry_code=None,
                source="baseline",
                metric=metric,
                value=None,
                unit="검사",
                status="unknown",
                row_ids=[],
            )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "CHECK"):
            register_fact(
                self.scope,
                industry_code=None,
                source="baseline",
                metric="typo",
                value=None,
                unit="검사",
                status="unknown",
                row_ids=[],
            )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "CHECK"), connect(self.path) as db:
            db.execute(
                "INSERT INTO scores VALUES(?,'I201','typo',0,'unknown',NULL,NULL,'[]')",
                (self.score_id,),
            )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "CHECK"), connect(self.path) as db:
            db.execute(
                "INSERT INTO agentic_runs VALUES('one',?,?,'typo','{}',NULL,'now')",
                (self.scope.snapshot_id, self.scope.run_id),
            )

    async def test_request_scoped_queries_use_indexes(self):
        queries = [
            (
                "idx_tool_calls_req",
                "SELECT reply_json FROM tool_calls WHERE request_id=? AND snapshot_id=? "
                "AND actor='decision' AND tool_name='get_facts'",
            ),
            (
                "idx_score_snapshots_req",
                "SELECT summary_json FROM score_snapshots WHERE request_id=? AND snapshot_id=? "
                "ORDER BY created_at DESC LIMIT 1",
            ),
            (
                "idx_advisor_consults_req",
                "SELECT consult_id FROM advisor_consults WHERE request_id=? AND snapshot_id=?",
            ),
        ]
        with connect(self.path) as db:
            for index, sql in queries:
                plan = db.execute(
                    "EXPLAIN QUERY PLAN " + sql, ("one", self.scope.snapshot_id)
                ).fetchall()
                with self.subTest(index=index):
                    self.assertTrue(any(index in row[3] for row in plan), plan)

    async def test_same_run_finish_preserves_partial_reasons(self):
        self.scope.incomplete("기존 수집 실패")
        await self.scope.finish()
        resumed = CaptureScope("one", self.path, self.scope.run_id, self.scope.snapshot_id)
        await resumed.finish()
        with connect(self.path) as db:
            manifest = json.loads(
                db.execute("SELECT base_source_manifest FROM snapshots").fetchone()[0]
            )
        run = manifest["runs"][self.scope.run_id]
        self.assertTrue(run["partial"])
        self.assertEqual(run["reasons"], ["기존 수집 실패"])

    async def pending_question(self):
        from app.services.analysis import execute_agentic_analysis
        from app.services.mock import dependencies

        waiting = await execute_agentic_analysis(
            "질문",
            request_id="resume",
            db_path=self.path,
            allow_questions=True,
            **dependencies(ask=True),
        )
        with connect(self.path) as db:
            run = db.execute(
                "SELECT snapshot_id,run_id,state_json FROM agentic_runs WHERE request_id='resume'"
            ).fetchone()
        scope = CaptureScope("resume", self.path, run[1], run[0])
        return scope, waiting.question_session_id, json.loads(run[2])

    async def test_concurrent_answer_loser_leaves_no_raw_response(self):
        from app.agents.agentic.questions import save_user_facts

        scope, question_id, state = await self.pending_question()
        replies = await asyncio.gather(
            *(
                asyncio.to_thread(
                    save_user_facts, scope, {"floor": value}, question_id, deepcopy(state)
                )
                for value in ("지상", "지하")
            ),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(reply, dict) for reply in replies), 1)
        self.assertEqual(sum(isinstance(reply, AnalysisConflictError) for reply in replies), 1)
        with connect(self.path) as db:
            count = db.execute(
                "SELECT count(*) FROM raw_responses WHERE request_id='resume' AND source='user'"
            ).fetchone()[0]
        self.assertEqual(count, 1)

    async def test_answer_fact_failure_rolls_back_raw_response(self):
        from app.agents.agentic.questions import save_user_facts

        scope, question_id, state = await self.pending_question()
        with (
            patch("app.agents.agentic.questions.register_fact", side_effect=OSError("저장 실패")),
            self.assertRaises(OSError),
        ):
            await asyncio.to_thread(save_user_facts, scope, {"floor": "지상"}, question_id, state)
        with connect(self.path) as db:
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM raw_responses WHERE request_id='resume' AND source='user'"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                db.execute(
                    "SELECT status FROM agentic_questions WHERE request_id='resume'"
                ).fetchone()[0],
                "waiting",
            )


class RemainingPolicyTests(unittest.TestCase):
    def test_top5_status_matches_rubric(self):
        self.assertTrue(evaluate({"address": "시험"})["top5_status"].startswith("v0.8"))

    def test_comparison_radius_crossing_seoul_boundary_is_reported(self):
        site = Site(input_address="시험", road_address="시험", latitude=37.5, longitude=127.091)
        rows = [
            {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[126.9, 37.4], [127.1, 37.4], [127.1, 37.6], [126.9, 37.6], [126.9, 37.4]]
                    ],
                }
            }
        ]
        self.assertEqual(boundary_limitations(rows, site.latitude, site.longitude, 500), [])
        adapter = LocalAdapter.__new__(LocalAdapter)
        adapter.versions = [
            {"source": source, "version_id": source, "quarter": "20262"}
            for source in ("stores", "lifecycle", "floating", "resident", "worker", "areas")
        ]
        adapter.rows = MagicMock(
            side_effect=lambda source, **kwargs: rows if source == "seoul_boundary" else []
        )
        adapter.stores = MagicMock(return_value=[])
        db = MagicMock()
        db.execute.return_value = []
        adapter.connection = MagicMock(return_value=nullcontext(db))
        task = AnalysisTask(request_id="one", site=site, radius_m=500)
        with (
            patch(
                "app.agents.commercial_area.config.Settings.from_env",
                return_value=SimpleNamespace(lq_radius_candidates=(1000,)),
            ),
            patch(
                "app.local_data.adapter.format_inputs",
                return_value=({"commercial_area": {}}, [], []),
            ),
            patch("app.agents.commercial_area.franchise.load_cached_brands", return_value={}),
        ):
            data = adapter.analyze(task)
        self.assertEqual(data["comparison_radius_m"], 1000)
        self.assertEqual(data["limitations"], ["서울 밖 점포 미반영"])
