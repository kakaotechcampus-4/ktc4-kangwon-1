"""사실 불변성·원문 계보·v0.8 경계와 기존 실행 비연결을 확인합니다."""

import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agentic.facts import register_fact
from app.agentic.scoring import WEIGHTS, rank_candidates, result, score_item, summarize
from app.agentic.snapshot import persist_snapshot_scores
from app.db.connection import connect, initialize
from app.db.repository import create_request
from app.schemas import AnalysisTask, Site
from app.storage.raw import RawStorageError, capture_scope


class ScoringPolicyTests(unittest.TestCase):
    def items(self, grades=None):
        grades = grades or {}
        return {
            key: result(key, grades.get(key, 4)) if key != "L" else result(key) for key in WEIGHTS
        }

    def test_status_and_applicable_weight(self):
        items = self.items()
        self.assertEqual(summarize("I201", items, "해당 없음")["applicable_weight"], 100)
        items["D2"] = result("D2", status="unknown")
        self.assertEqual(summarize("I201", items, "해당 없음")["applicable_weight"], 100)
        items["D2"] = result("D2", status="n.a.")
        self.assertEqual(summarize("I201", items, "해당 없음")["applicable_weight"], 90)

    def test_recommendation_lower_boundary(self):
        items = self.items({"D1": 2, "D2": 2, "D3": 2, "D4": 2, "S1": 3, "S2": 3, "S3": 3, "S4": 3})
        self.assertEqual(summarize("I201", items, "해당 없음")["lower_ratio"], 0.65)
        self.assertEqual(summarize("I201", items, "해당 없음")["badge"], "추천")
        items["D4"] = result("D4", 1)
        self.assertEqual(summarize("I201", items, "해당 없음")["badge"], "보류")

    def test_minimum_applicable_weight(self):
        items = self.items()
        for key in ("D2", "D3", "C1", "D4"):
            items[key] = result(key, status="n.a.")
        row = summarize("I201", items, "해당 없음")
        self.assertEqual(row["applicable_weight"], 60)
        self.assertEqual(row["badge"], "추천")
        items = self.items()
        for key in ("D2", "D3", "C4", "D4", "S1"):
            items[key] = result(key, status="n.a.")
        self.assertEqual(summarize("I201", items, "해당 없음")["badge"], "조건부")

    def test_upper_boundary_and_prohibition(self):
        items = self.items(
            {
                "D1": 1,
                "D2": 1,
                "D3": 1,
                "D4": 0,
                "C1": 2,
                "C4": 2,
                "S1": 2,
                "S2": 2,
                "S3": 2,
                "S4": 2,
            }
        )
        row = summarize("I201", items, "해당 없음")
        self.assertEqual(row["upper_ratio"], 0.45)
        self.assertEqual(row["badge"], "비추천")
        items["D4"] = result("D4", 1)
        self.assertEqual(summarize("I201", items, "해당 없음")["badge"], "보류")
        self.assertEqual(summarize("I101", self.items(), "금지")["badge"], "비추천")

    def test_rank_ties(self):
        rows = [
            {"code": c, "lower": b, "coverage": v, "regulation": "해당 없음"}
            for c, b, v in [
                ("G205", 10, 0.9),
                ("G204", 10, 0.9),
                ("I201", 10, 0.8),
                ("G209", 11, 0.1),
            ]
        ]
        self.assertEqual(
            [r["code"] for r in rank_candidates(rows)], ["G209", "G204", "G205", "I201"]
        )

    def test_partial_source_increases_unknown(self):
        from app.agents.commercial_area.baseline import SEOUL_INDUSTRY_DENSITY_PERCENTILES
        from app.agents.floating_population.baseline import DAILY_TOTAL_PERCENTILES

        sample = {
            "commercial_area": {
                "radius_m": 500,
                "by_middle": [
                    {
                        "code": "G204",
                        "density_per_km2": SEOUL_INDUSTRY_DENSITY_PERCENTILES["G204"][50],
                    }
                ],
            },
            "commercial_collection_complete": True,
            "floating_population": {
                "benchmark": {"mean_daily_per_trade_area": DAILY_TOTAL_PERCENTILES[50]}
            },
        }
        self.assertEqual(score_item("C1", {}, "G204", sample)["status"], "observed")
        sample["runtime_partial_sources"] = ["commercial_area"]
        self.assertEqual(score_item("C1", {}, "G204", sample)["status"], "unknown")


class FactRegistryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = initialize(Path(self.tmp.name) / "facts.sqlite3")
        create_request("facts", "서울 목업", db_path=self.path)

    def tearDown(self):
        self.tmp.cleanup()

    async def test_fact_identity_and_lineage(self):
        async with capture_scope("facts", self.path) as scope:
            await scope.record(
                source="commercial_area",
                source_type="api",
                args={},
                page="1",
                status=200,
                payload={"rows": [{"bizesId": "store", "indsMclsCd": "I201"}]},
            )
            with connect(self.path) as db:
                ref = db.execute("SELECT raw_row_id FROM raw_rows").fetchone()[0]
            kwargs = dict(
                industry_code="I201",
                source="commercial_area",
                metric="density_per_km2",
                value=2.0,
                unit="개/km²",
                status="observed",
                row_ids=[ref],
            )
            first = await asyncio.to_thread(register_fact, scope, **kwargs)
            same = await asyncio.to_thread(register_fact, scope, **kwargs)
            second = await asyncio.to_thread(register_fact, scope, **(kwargs | {"value": 3.0}))
            self.assertEqual(first, same)
            self.assertNotEqual(first, second)
        with connect(self.path) as db:
            self.assertEqual(
                db.execute(
                    "SELECT raw_row_id FROM fact_sources WHERE fact_id=?", (first,)
                ).fetchone()[0],
                ref,
            )
            self.assertEqual(
                json.loads(
                    db.execute("SELECT value_json FROM facts WHERE fact_id=?", (first,)).fetchone()[
                        0
                    ]
                ),
                2.0,
            )
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE facts SET value_json='4' WHERE fact_id=?", (first,))

    async def test_persist_code_scores_and_unreviewed_L(self):
        task = AnalysisTask(
            request_id="facts",
            site=Site(input_address="서울", road_address="서울", latitude=37.5, longitude=127.0),
            radius_m=500,
        )
        async with capture_scope("facts", self.path):
            score_id = await persist_snapshot_scores(task)
        with connect(self.path) as db:
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM scores WHERE score_snapshot_id=?", (score_id,)
                ).fetchone()[0],
                561,
            )
            rows = db.execute(
                "SELECT status,grade,points,fact_ids_json FROM scores WHERE item='L'"
            ).fetchall()
            self.assertTrue(all(tuple(r) == ("unknown", None, None, "[]") for r in rows))
            self.assertEqual(
                db.execute("SELECT L_review_state FROM score_snapshots").fetchone()[0], "unreviewed"
            )

    async def test_unrelated_c1_is_cited_to_industry_profile(self):
        from app.agentic.contracts import ScoreItem

        task = AnalysisTask(
            request_id="facts",
            site=Site(input_address="서울", road_address="서울", latitude=37.5, longitude=127.0),
            radius_m=500,
        )
        async with capture_scope("facts", self.path):
            await persist_snapshot_scores(task)
        with connect(self.path) as db:
            rows = db.execute(
                "SELECT industry_code,status,grade,points,fact_ids_json FROM scores "
                "WHERE item='C1' AND industry_code='M103'"
            ).fetchall()
            self.assertEqual(len(rows), 1)
            code, status, grade, points, fact_ids = rows[0]
            fact_ids = json.loads(fact_ids)
            self.assertEqual((status, grade, points), ("observed", 2, 7.5))
            self.assertTrue(fact_ids)
            fact = db.execute(
                "SELECT source,metric,status FROM facts WHERE fact_id=?", (fact_ids[0],)
            ).fetchone()
            self.assertEqual(tuple(fact), ("industry_profile", "competition_index", "observed"))
        ScoreItem(item="C1", status=status, grade=grade, points=points, fact_ids=fact_ids)

    async def test_scoring_failure_marks_service_failed(self):
        from app.services.analysis import execute_agentic_analysis
        from app.services.mock import dependencies

        with (
            patch("app.agentic.snapshot._persist", side_effect=ValueError("secret")),
            self.assertRaises(RawStorageError),
        ):
            await execute_agentic_analysis(
                "서울",
                request_id="score-failed",
                db_path=self.path,
                **dependencies(),
            )
        with connect(self.path) as db:
            row = db.execute(
                "SELECT status,error_json FROM analysis_requests WHERE request_id='score-failed'"
            ).fetchone()
            self.assertEqual(row[0], "failed")
            self.assertNotIn("secret", row[1])
