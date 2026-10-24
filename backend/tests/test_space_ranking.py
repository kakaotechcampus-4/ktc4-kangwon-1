"""공간 판정을 순위·배지에 반영하고 화면 점수는 그대로 두는지 검증합니다."""

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from app.agentic.facts import register_fact
from app.agentic.questions import save_confirmed_space
from app.agentic.report import complete_l_records, load_base, recompute_l_scores
from app.agentic.scoring import (
    WEIGHTS,
    apply_space,
    evaluate,
    rank_candidates,
    rank_key,
    result,
    summarize,
)
from app.agentic.snapshot import persist_report, persist_space_requirements
from app.agentic.space import ensure_space_fits, rule_answers
from app.agentic.space_rules import SpaceJudgement, judge, load_requirements
from app.db.connection import connect, initialize
from app.db.repository import create_request
from app.industries.catalog import INDUSTRIES
from app.storage.raw import capture_scope


def space(adjustment=0, excluded=False, notes=()):
    return {
        "excluded": excluded,
        "exclusion_reasons": ["배기(덕트) 설치 불가"] if excluded else [],
        "adjustment": adjustment,
        "notes": list(notes),
    }


def row(code, lower, coverage=0.9, regulation="해당 없음", **extra):
    return {"code": code, "lower": lower, "coverage": coverage, "regulation": regulation, **extra}


def items(grade=4):
    return {key: result(key, grade) if key != "L" else result(key) for key in WEIGHTS}


class RankTests(unittest.TestCase):
    def test_rank_uses_hidden_adjustment(self):
        cafe = row("I212", 72, space=space(-10))
        retail = row("G204", 68)
        self.assertEqual([r["code"] for r in rank_candidates([cafe, retail])], ["G204", "I212"])
        self.assertEqual((cafe["lower"], retail["lower"]), (72, 68))
        self.assertEqual(rank_key(cafe), (-62, -0.9, "I212"))
        self.assertEqual(rank_key(retail), (-68, -0.9, "G204"))

    def test_space_excluded_not_in_top5(self):
        korean = row("I201", 90, space=space(excluded=True))
        self.assertEqual([r["code"] for r in rank_candidates([korean, row("G204", 10)])], ["G204"])

    def test_regulation_ban_still_excluded(self):
        lodging = row("I101", 95, regulation="금지")
        self.assertEqual([r["code"] for r in rank_candidates([lodging, row("G204", 1)])], ["G204"])


class ApplySpaceTests(unittest.TestCase):
    def test_note_downgrades_recommend_badge(self):
        base = summarize("I201", items(), "해당 없음")
        self.assertEqual(base["badge"], "추천")
        before = deepcopy(base)
        applied = apply_space(base, SpaceJudgement(False, (), 0, ("배기(덕트) 확인 필요",)))
        self.assertEqual(applied["badge"], "조건부")
        self.assertEqual(applied["confirmation_conditions"][-1], "배기(덕트) 확인 필요")
        self.assertEqual(applied["space"], space(notes=["배기(덕트) 확인 필요"]))
        self.assertEqual((applied["lower"], applied["upper"]), (base["lower"], base["upper"]))
        self.assertEqual(base, before)

    def test_no_note_keeps_badge(self):
        base = summarize("I201", items(), "해당 없음")
        applied = apply_space(base, SpaceJudgement(False, (), -7, ()))
        self.assertEqual(applied["badge"], "추천")
        self.assertEqual(applied["confirmation_conditions"], base["confirmation_conditions"])
        self.assertEqual(applied["space"], space(-7))

    def test_excluded_row_carries_reasons(self):
        base = summarize("I201", items(), "해당 없음")
        applied = apply_space(base, SpaceJudgement(True, ("배기(덕트) 설치 불가",), 0, ()))
        self.assertEqual(applied["space"], space(excluded=True))
        self.assertEqual(applied["badge"], "추천")

    def test_no_input_order_unchanged(self):
        requirements = load_requirements()
        rows = []
        for index, code in enumerate(sorted(INDUSTRIES)):
            grades = {key: (index * 7 + n) % 5 for n, key in enumerate(WEIGHTS) if key != "L"}
            scored = {
                key: result(key, grades[key]) if key != "L" else result(key) for key in WEIGHTS
            }
            rows.append(
                apply_space(summarize(code, scored, "해당 없음"), judge(requirements[code], {}))
            )
        old = sorted(rows, key=lambda r: (-r["lower"], -(r["coverage"] or 0), r["code"]))[:5]
        self.assertEqual([r["code"] for r in rank_candidates(rows)], [r["code"] for r in old])

    def test_evaluate_attaches_space_without_answers(self):
        report = evaluate({"address": "시험"})
        self.assertEqual(len(report["rows"]), len(INDUSTRIES))
        for scored in report["rows"]:
            with self.subTest(code=scored["code"]):
                self.assertFalse(scored["space"]["excluded"])
                self.assertEqual(scored["space"]["adjustment"], 0)
        korean = next(r for r in report["rows"] if r["code"] == "I201")
        self.assertIn("배기(덕트) 확인 필요", korean["space"]["notes"])
        self.assertIn("배기(덕트) 확인 필요", korean["confirmation_conditions"])


class RecomputeSpaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "db.sqlite3"
        initialize(self.path)
        create_request("space", "시험", db_path=self.path)
        self.manager = capture_scope("space", self.path)
        self.scope = await self.manager.__aenter__()
        rows = [
            summarize(code, {key: result(key) for key in WEIGHTS}, "해당 없음")
            for code in INDUSTRIES
        ]
        persist_report(self.scope, {"rows": rows, "top5": rows[:5]}, {}, [])
        persist_space_requirements(self.scope)

    async def asyncTearDown(self):
        await self.manager.__aexit__(None, None, None)
        self.temp.cleanup()

    def ai_answer(self, metric, value):
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

    def recompute(self):
        base_id, base_rows = load_base(self.scope)
        records = complete_l_records((), base_id, base_rows)
        score_id, rows = recompute_l_scores(self.scope, records, base_id, base_rows)
        return score_id, {r["code"]: r for r in rows}, rows

    async def test_rule_answers_use_latest_readable_floor(self):
        save_confirmed_space(
            self.scope, {"floor": "4층", "existing_facilities": {"ventilation": "unavailable"}}
        )
        self.ai_answer("floor", "1층")
        self.ai_answer("floor", "높은 층")
        self.ai_answer("existing_facilities", "배기 있음")
        self.assertEqual(
            rule_answers(self.scope),
            {"floor": "1층", "confirmed_facilities": {"ventilation": "unavailable"}},
        )

    async def test_recompute_applies_confirmed_space(self):
        save_confirmed_space(
            self.scope, {"floor": "4층", "existing_facilities": {"ventilation": "unavailable"}}
        )
        score_id, by_code, rows = self.recompute()
        self.assertTrue(by_code["I201"]["space"]["excluded"])
        self.assertEqual(by_code["G204"]["space"]["adjustment"], -10)
        top = [r["code"] for r in rank_candidates(rows)]
        self.assertNotIn("I201", top)
        with connect(self.path) as db:
            stored = db.execute(
                "SELECT top5_json FROM score_snapshots WHERE score_snapshot_id=?", (score_id,)
            ).fetchone()[0]
        self.assertEqual(json.loads(stored), top)

    async def test_recompute_uses_readable_landlord_floor_answer(self):
        self.ai_answer("floor", "4층")
        self.ai_answer("existing_facilities", "배기 없음")
        _, by_code, _ = self.recompute()
        self.assertEqual(by_code["G204"]["space"]["adjustment"], -10)
        self.assertNotIn("층 확인 필요", by_code["G204"]["space"]["notes"])
        self.assertTrue(by_code["S203"]["space"]["excluded"])
        self.assertFalse(by_code["I201"]["space"]["excluded"])

    async def test_unreadable_floor_answer_stays_unconfirmed(self):
        self.ai_answer("floor", "높은 층")
        _, by_code, _ = self.recompute()
        self.assertEqual(by_code["G204"]["space"]["adjustment"], 0)
        self.assertIn("층 확인 필요", by_code["G204"]["space"]["notes"])

    async def test_space_fit_and_rules_read_the_same_floor(self):
        save_confirmed_space(self.scope, {"floor": "1층"})
        self.ai_answer("floor", "4층")
        current = ensure_space_fits(self.scope)
        with connect(self.path) as db:
            value = db.execute(
                "SELECT value_json FROM facts WHERE fact_id=?", (current["G204"],)
            ).fetchone()[0]
        self.assertEqual(json.loads(value)["floor"], "불일치")
        _, by_code, _ = self.recompute()
        self.assertEqual(by_code["G204"]["space"]["adjustment"], -10)
