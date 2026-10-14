"""공간 비교의 미확인 처리·부모 계보·답변 후 불변 갱신을 검증합니다."""

import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agentic.contracts import GetFactsInput
from app.agentic.facts import register_fact
from app.agentic.questions import save_user_facts
from app.agentic.read_tools import get_facts
from app.agentic.snapshot import persist_space_requirements
from app.agentic.space import compare_space, ensure_space_fits
from app.canonical import canonical_json
from app.db.connection import connect, initialize
from app.db.repository import create_request
from app.storage.raw import capture_scope


class CompareSpaceTests(unittest.TestCase):
    def test_combined_facility_absence_and_explicit_approximate_area(self):
        for answer in ("이전 일반 소매, 주방·배기 없음", "주방·배기 설비 없음"):
            with self.subTest(answer=answer):
                result = compare_space(
                    {
                        "floor_preference": "1층 접근 우선 가정",
                        "area_band": "20~40㎡",
                        "kitchen_needed": "true",
                        "ventilation_needed": "true",
                    },
                    {"floor": "1층", "exclusive_area": "약40㎡", "existing_facilities": answer},
                )
                self.assertEqual(result["floor"], "일치")
                self.assertEqual(result["area"], "일치")
                self.assertEqual(result["kitchen"], "불일치")
                self.assertEqual(result["ventilation"], "불일치")
                self.assertEqual(result["water_supply"], "미확인")

    def test_only_explicit_requirements_and_answers_are_compared(self):
        result = compare_space(
            {
                "floor_preference": "1층",
                "area_band": "20~40㎡",
                "kitchen_needed": "true",
                "ventilation_needed": "true",
                "water_supply_needed": "true",
                "reviewed": False,
                "confidence": "low",
            },
            {
                "floor": "2층",
                "exclusive_area": "30㎡",
                "existing_facilities": "주방 있음; 배기 없음; 급배수 있음",
            },
        )
        self.assertEqual(
            {k: result[k] for k in ("floor", "area", "kitchen", "ventilation", "water_supply")},
            {
                "floor": "불일치",
                "area": "일치",
                "kitchen": "일치",
                "ventilation": "불일치",
                "water_supply": "일치",
            },
        )
        self.assertFalse(result["reviewed"])
        self.assertEqual(result["confidence"], "low")

    def test_false_conditions_cannot_become_adverse(self):
        result = compare_space(
            {"kitchen_needed": "false", "ventilation_needed": "false"},
            {"existing_facilities": "주방 없음; 배기 없음"},
        )
        self.assertEqual(result["kitchen"], "해당 없음")
        self.assertEqual(result["ventilation"], "해당 없음")
        self.assertEqual(result["water_supply"], "미확인")

    def test_ambiguous_profile_and_answers_do_not_invent_thresholds(self):
        result = compare_space(
            {
                "floor_preference": "이동 편의 우선 가정",
                "area_band": "20좌석 구성별 확인",
                "kitchen_needed": "conditional",
                "ventilation_needed": "true",
            },
            {
                "floor": "1층",
                "exclusive_area": "30㎡",
                "existing_facilities": "주방 있음; 배기 설치 가능",
            },
        )
        self.assertTrue(
            all(
                result[k] == "미확인"
                for k in ("floor", "area", "kitchen", "ventilation", "water_supply")
            )
        )
        result = compare_space(
            {"floor_preference": "1층", "area_band": "20~40㎡"},
            {"floor": "아마 1층", "exclusive_area": "30평"},
        )
        self.assertEqual(result["floor"], "미확인")
        self.assertEqual(result["area"], "미확인")


class SpaceFitFactsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = initialize(Path(self.temp.name) / "requests.sqlite3")
        create_request("space", "시험", db_path=self.path)
        self.manager = capture_scope("space", self.path)
        self.scope = await self.manager.__aenter__()
        await asyncio.to_thread(persist_space_requirements, self.scope)

    async def asyncTearDown(self):
        await self.manager.__aexit__(None, None, None)
        self.temp.cleanup()

    def user_fact(self, metric, value):
        response = self.scope.record_sync(
            source="user",
            source_type="api",
            args={},
            page="answer",
            status=200,
            payload={"rows": [{metric: value}]},
        )
        with connect(self.path) as db:
            ref = db.execute(
                "SELECT raw_row_id FROM raw_response_rows WHERE response_id=?", (response,)
            ).fetchone()[0]
        return register_fact(
            self.scope,
            industry_code=None,
            source="user",
            metric=metric,
            value=value,
            unit="임대인 답변",
            status="observed",
            row_ids=[ref],
        )

    async def test_all_51_unknown_values_and_parents_are_preserved(self):
        first = await asyncio.to_thread(ensure_space_fits, self.scope)
        self.assertEqual(len(first), 51)
        self.assertEqual(first, await asyncio.to_thread(ensure_space_fits, self.scope))
        with connect(self.path) as db:
            rows = db.execute(
                "SELECT status,citable,value_json FROM facts WHERE metric='space_fit'"
            ).fetchall()
            self.assertEqual(len(rows), 51)
            self.assertTrue(all(row[0] == "unknown" and row[1] == 0 for row in rows))
            self.assertTrue(all(json.loads(row[2])["water_supply"] == "미확인" for row in rows))
            self.assertEqual(db.execute("SELECT count(*) FROM fact_parents").fetchone()[0], 51)
            self.assertEqual(db.execute("SELECT count(*) FROM space_fit_current").fetchone()[0], 51)
            retail = json.loads(
                db.execute(
                    "SELECT value_json FROM facts WHERE fact_id=?", (first["G204"],)
                ).fetchone()[0]
            )
            self.assertEqual(retail["kitchen"], "해당 없음")

    async def test_changed_answer_creates_new_fact_and_updates_only_the_pointer(self):
        await asyncio.to_thread(self.user_fact, "floor", "1층")
        first = await asyncio.to_thread(ensure_space_fits, self.scope)
        parent = await asyncio.to_thread(self.user_fact, "floor", "2층")
        second = await asyncio.to_thread(ensure_space_fits, self.scope)
        self.assertNotEqual(first["G204"], second["G204"])
        result = await get_facts(
            self.scope,
            GetFactsInput(source="industry_profile", metrics=["space_fit"], limit=51),
        )
        self.assertEqual(len(result.facts), 51)
        self.assertEqual({f.fact_id for f in result.facts}, set(second.values()))
        self.assertNotIn(first["G204"], {f.fact_id for f in result.facts})
        with connect(self.path) as db:
            for fact_id, expected in ((first["G204"], "일치"), (second["G204"], "불일치")):
                row = db.execute(
                    "SELECT status,citable,value_json FROM facts WHERE fact_id=?", (fact_id,)
                ).fetchone()
                self.assertEqual(
                    (row[0], row[1], json.loads(row[2])["floor"]), ("observed", 1, expected)
                )
            self.assertEqual(
                db.execute(
                    "SELECT fact_id FROM space_fit_current WHERE industry_code='G204'"
                ).fetchone()[0],
                second["G204"],
            )
            self.assertIn(
                parent,
                [
                    r[0]
                    for r in db.execute(
                        "SELECT parent_fact_id FROM fact_parents WHERE fact_id=?", (second["G204"],)
                    )
                ],
            )
            for sql in (
                "UPDATE fact_parents SET parent_fact_id=parent_fact_id",
                "DELETE FROM fact_parents",
            ):
                with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql)

    async def test_parent_scope_is_checked_before_inserting_a_child(self):
        parent = await asyncio.to_thread(self.user_fact, "floor", "1층")
        create_request("other", "시험", db_path=self.path)
        async with capture_scope("other", self.path) as other:
            with self.assertRaises(ValueError):
                await asyncio.to_thread(
                    register_fact,
                    other,
                    industry_code="G204",
                    source="industry_profile",
                    metric="space_fit",
                    value={"floor": "일치"},
                    unit="비교",
                    status="observed",
                    row_ids=[],
                    parent_fact_ids=[parent],
                )
            with connect(self.path) as db:
                self.assertEqual(
                    db.execute("SELECT count(*) FROM facts WHERE request_id='other'").fetchone()[0],
                    0,
                )

    async def test_cancelled_comparison_does_not_leave_partial_pointers(self):
        self.scope.cancelled.set()
        try:
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.to_thread(ensure_space_fits, self.scope)
        finally:
            self.scope.cancelled.clear()
        with connect(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM space_fit_current").fetchone()[0], 0)
            self.assertEqual(
                db.execute("SELECT count(*) FROM facts WHERE metric='space_fit'").fetchone()[0], 0
            )

    async def test_unknown_value_opt_in_keeps_the_existing_default(self):
        normal = register_fact(
            self.scope,
            industry_code=None,
            source="user",
            metric="space_condition",
            value={"state": "미확인"},
            unit="조건",
            status="unknown",
            row_ids=[],
        )
        with connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT value_json FROM facts WHERE fact_id=?", (normal,)).fetchone()[0],
                "null",
            )
        with self.assertRaises(ValueError):
            register_fact(
                self.scope,
                industry_code=None,
                source="user",
                metric="space_condition",
                value={"state": "미확인"},
                unit="조건",
                status="unknown",
                row_ids=[],
                retain_unknown_value=True,
            )

    async def test_an_existing_child_cannot_gain_another_parent(self):
        current = await asyncio.to_thread(ensure_space_fits, self.scope)
        extra = await asyncio.to_thread(self.user_fact, "floor", "1층")
        with connect(self.path) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO fact_parents VALUES(?,?)", (current["G204"], extra))

    async def test_question_answers_and_comparisons_commit_together(self):
        await asyncio.to_thread(ensure_space_fits, self.scope)
        saved = {
            "messages": [
                {
                    "role": "tool",
                    "content": canonical_json(
                        {"status": "ok", "data": {"question_session_id": "q"}, "fact_ids": []}
                    ),
                }
            ]
        }
        with connect(self.path) as db:
            db.execute("UPDATE analysis_requests SET status='waiting_for_input'")
            db.execute(
                "INSERT INTO agentic_questions VALUES(?,?,?,?,?,?,?)",
                (
                    "q",
                    "space",
                    self.scope.snapshot_id,
                    '[{"field":"floor"}]',
                    "{}",
                    "waiting",
                    "now",
                ),
            )
            db.execute(
                "INSERT INTO agentic_runs VALUES(?,?,?,?,?,?,?)",
                (
                    "space",
                    self.scope.snapshot_id,
                    self.scope.run_id,
                    "waiting_for_input",
                    canonical_json(saved),
                    None,
                    "now",
                ),
            )
        with patch(
            "app.agentic.questions.ensure_space_fits", side_effect=RuntimeError("비교 저장 실패")
        ):
            with self.assertRaises(RuntimeError):
                await asyncio.to_thread(save_user_facts, self.scope, {"floor": "1층"}, "q", saved)
        with connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT status FROM agentic_questions").fetchone()[0], "waiting"
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM facts WHERE source='user'").fetchone()[0], 0
            )
        await asyncio.to_thread(save_user_facts, self.scope, {"floor": "1층"}, "q", saved)
        with connect(self.path) as db:
            value = db.execute(
                "SELECT f.value_json FROM space_fit_current p JOIN facts f USING(fact_id) "
                "WHERE p.industry_code='G204'"
            ).fetchone()[0]
            self.assertEqual(json.loads(value)["floor"], "일치")
