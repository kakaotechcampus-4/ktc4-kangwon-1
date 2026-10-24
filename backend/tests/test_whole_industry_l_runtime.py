"""전체 업종 L의 단계·부분 채택·종료·재개를 외부 호출 없이 검증합니다."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.agentic.facts import register_fact
from app.agentic.runtime import DecisionLoop
from app.agentic.scoring import WEIGHTS, result, summarize
from app.agentic.snapshot import persist_report
from app.db.connection import connect, initialize
from app.db.repository import create_request
from app.industries.catalog import INDUSTRIES
from app.schemas import Site
from app.storage.raw import capture_scope


class WholeIndustryLTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = initialize(Path(self.temp.name) / "requests.sqlite3")
        create_request("whole", "시험", db_path=self.path)
        self.manager = capture_scope("whole", self.path)
        self.scope = await self.manager.__aenter__()
        self.site = Site(input_address="시험", road_address="시험", latitude=37.5, longitude=127.0)
        rows = [
            summarize(code, {key: result(key) for key in WEIGHTS}, "해당 없음")
            for code in INDUSTRIES
        ]
        self.base_id = persist_report(self.scope, {"rows": rows, "top5": rows[:5]}, {}, [])
        self.loop = await DecisionLoop.create(self.scope, self.site)

    async def asyncTearDown(self):
        await self.manager.__aexit__(None, None, None)
        self.temp.cleanup()

    def unknown(self, code):
        return {
            "industry_code": code,
            "note": "확인된 새 근거가 없습니다.",
        }

    async def submit(self, codes=(), finish=False):
        return await self.loop.tools.execute(
            "submit_l", {"L_records": [self.unknown(code) for code in codes], "finish": finish}
        )

    async def test_report_tool_is_closed_until_l_stage_ends(self):
        names = [d["function"]["name"] for d in self.loop.definitions()]
        self.assertNotIn("submit_draft", names)
        self.assertIn("submit_l", names)
        reply = await self.loop.submit_draft(SimpleNamespace(phase="draft", report=None))
        self.assertEqual(reply.status, "error")

    async def test_three_batches_complete_all_industries_and_recompute_scores(self):
        codes = list(INDUSTRIES)
        for offset in range(0, 51, 17):
            reply = await self.submit(codes[offset : offset + 17])
            self.assertEqual(reply.status, "ok", reply.error)
            self.assertEqual(reply.data.submitted_count, offset + 17)
            self.assertEqual(reply.data.remaining_count, 51 - offset - 17)
        self.assertTrue(reply.data.closed)
        self.assertTrue(reply.data.score_snapshot_id)
        self.assertEqual(len(reply.data.scorecard.summaries), 5)
        self.assertEqual(len(self.loop.state["L_records"]), 51)
        names = [d["function"]["name"] for d in self.loop.definitions()]
        self.assertIn("submit_draft", names)
        self.assertNotIn("submit_l", names)
        self.assertEqual((await self.submit(finish=True)).status, "ok")

    async def test_single_batch_accepts_all_industries(self):
        reply = await self.submit(list(INDUSTRIES))
        self.assertEqual(reply.status, "ok", reply.error)
        self.assertEqual(len(reply.data.accepted), 51)
        self.assertTrue(reply.data.closed)

    async def test_duplicate_is_ignored_and_other_rows_are_accepted(self):
        codes = list(INDUSTRIES)
        self.assertEqual((await self.submit(codes[:1])).status, "ok")
        invalid = await self.submit(codes[:2])
        self.assertEqual(invalid.status, "ok", invalid.error)
        self.assertEqual(invalid.data.ignored, [codes[0]])
        self.assertEqual(invalid.data.accepted, [codes[1]])
        self.assertEqual(set(self.loop.state["L_records"]), set(codes[:2]))

    async def test_finish_fills_individual_unknown_reasons_and_persists(self):
        reply = await self.submit(list(INDUSTRIES)[:1], finish=True)
        self.assertEqual(reply.status, "ok", reply.error)
        self.assertEqual(len(self.loop.state["L_records"]), 51)
        self.assertTrue(all(r["limitations"] for r in self.loop.state["L_records"].values()))
        await self.loop.save()
        with connect(self.path) as db:
            saved = json.loads(db.execute("SELECT state_json FROM agentic_runs").fetchone()[0])
        self.assertEqual(saved["L_records"], self.loop.state["L_records"])
        self.assertTrue(saved["L_closed"])

    async def test_initial_context_contains_entire_scope_without_top_ten_restriction(self):
        context = json.loads(self.loop.state["messages"][1]["content"])
        self.assertNotIn("L_top10", context)
        self.assertEqual(set(context["L_industry_codes"]), set(INDUSTRIES))

    async def observed(self, code, value="지상", read=True, metric="space_condition"):
        response = await self.scope.record(
            source="user",
            source_type="api",
            args={},
            page="space",
            status=200,
            payload={"rows": [{metric: value}]},
        )
        with connect(self.path) as db:
            ref = db.execute(
                "SELECT raw_row_id FROM raw_response_rows WHERE response_id=?", (response,)
            ).fetchone()[0]
        fact = register_fact(
            self.scope,
            industry_code=code,
            source="user",
            metric=metric,
            value=value,
            unit="임대인 답변",
            status="observed",
            row_ids=[ref],
            field_pointer="/" + metric,
        )
        if read:
            await self.loop.tools.execute("get_facts", {"fact_ids": [fact]})
        return {"industry_code": code, "factors": [{"fact_id": fact, "direction": "favorable"}]}

    async def test_low_code_rank_can_submit_observed_l_and_fallback_preserves_it(self):
        record = await self.observed("S209")
        reply = await self.loop.tools.execute("submit_l", {"L_records": [record]})
        self.assertEqual(reply.status, "ok", reply.error)
        output = await self.loop.fallback("대역 종료")
        by_code = {r.industry_code: r for r in output.result.L_records}
        self.assertEqual(len(by_code), 51)
        self.assertEqual(by_code["S209"].grade, 3)
        self.assertTrue(all(r.limitations for r in by_code.values() if r.status == "unknown"))
        self.assertEqual(output.result.top5[0].industry_code, "S209")

    async def test_invalid_evidence_rejects_only_its_row(self):
        codes = list(INDUSTRIES)
        record = await self.observed("S209")
        record["factors"][0]["fact_id"] = "badalias"
        reply = await self.loop.tools.execute(
            "submit_l", {"L_records": [self.unknown(codes[0]), record]}
        )
        self.assertEqual(reply.status, "ok", reply.error)
        self.assertEqual(reply.data.accepted, [codes[0]])
        self.assertEqual(reply.data.rejected[0]["industry_code"], "S209")
        self.assertIn("correction", reply.data.rejected[0])
        self.assertEqual(set(self.loop.state["L_records"]), {codes[0]})

    async def test_unread_evidence_is_rejected_and_valid_row_is_preserved(self):
        record = await self.observed("S209", read=False)
        valid = self.unknown("G204")
        reply = await self.loop.tools.execute("submit_l", {"L_records": [record, valid]})
        self.assertEqual(reply.status, "ok", reply.error)
        self.assertEqual(reply.data.accepted, ["G204"])
        self.assertEqual(reply.data.rejected[0]["industry_code"], "S209")

    async def test_neutral_and_severe_grades_are_calculated_from_evidence(self):
        neutral = await self.observed("S209")
        neutral = {
            "industry_code": "S209",
            "neutral": True,
            "fact_ids": [neutral["factors"][0]["fact_id"]],
        }
        severe = await self.observed("I201")
        severe["factors"][0].update(direction="adverse", severe=True)
        reply = await self.loop.tools.execute("submit_l", {"L_records": [neutral, severe]})
        self.assertEqual(reply.status, "ok", reply.error)
        self.assertEqual(reply.data.rejected, [])
        self.assertEqual(self.loop.state["L_records"]["S209"]["grade"], 2)
        self.assertEqual(self.loop.state["L_records"]["I201"]["grade"], 0)

    async def test_report_submission_preserves_closed_l_records(self):
        record = await self.observed("S209")
        await self.loop.tools.execute("submit_l", {"L_records": [record], "finish": True})
        before = json.loads(json.dumps(self.loop.state["L_records"]))
        reply = await self.loop.tools.execute("submit_draft", {"phase": "draft", "report": {}})
        self.assertEqual(reply.status, "ok", reply.error)
        self.assertEqual(self.loop.state["L_records"], before)
        self.assertEqual(
            next(r.grade for r in self.loop.done.L_records if r.industry_code == "S209"), 3
        )

    async def test_retail_no_kitchen_cannot_become_adverse_user_factor(self):
        record = await self.observed("G204", "주방 없음")
        record["factors"][0]["direction"] = "adverse"
        reply = await self.loop.tools.execute("submit_l", {"L_records": [record]})
        self.assertEqual(reply.status, "ok", reply.error)
        self.assertEqual(reply.data.rejected[0]["industry_code"], "G204")
        self.assertEqual(self.loop.state["L_records"], {})

    async def test_bulk_space_fits_keep_every_industry_and_draft_flags(self):
        reply = await self.loop.tools.execute(
            "get_facts", {"source": "industry_profile", "metrics": ["space_fit"], "limit": 51}
        )
        compact = await self.loop.compact_reply(reply, "get_facts", {})
        facts = compact["data"]["facts"]
        self.assertEqual(len(facts), 51)
        self.assertEqual({fact["industry_code"] for fact in facts}, set(INDUSTRIES))
        self.assertTrue(
            all("reviewed" in fact["value"] and "confidence" in fact["value"] for fact in facts)
        )
        self.assertLessEqual(len(json.dumps(compact, ensure_ascii=False)), 16000)

    async def test_space_fit_factor_infers_confirmed_matching_component(self):
        record = await self.observed("G204")
        user_fact = record["factors"][0]["fact_id"]
        with connect(self.path) as db:
            profile = db.execute(
                "SELECT fact_id FROM facts WHERE source='industry_profile' "
                "AND metric='space_requirements' AND industry_code='G204'"
            ).fetchone()[0]
        fact = register_fact(
            self.scope,
            industry_code="G204",
            source="industry_profile",
            metric="space_fit",
            value={
                "floor": "일치",
                "area": "일치",
                "kitchen": "해당 없음",
                "ventilation": "해당 없음",
                "water_supply": "미확인",
                "reviewed": False,
                "confidence": "low",
            },
            unit="공간 비교",
            status="observed",
            row_ids=[],
            parent_fact_ids=[profile, user_fact],
        )
        await self.loop.tools.execute("get_facts", {"fact_ids": [fact]})
        record["factors"][0].update(fact_id=fact, direction="adverse")
        reply = await self.loop.tools.execute("submit_l", {"L_records": [record]})
        self.assertEqual(reply.data.accepted, [])
        self.assertEqual(reply.data.rejected[0]["industry_code"], "G204")
        self.assertEqual(self.loop.state["L_records"], {})
        record["factors"][0]["direction"] = "favorable"
        reply = await self.loop.tools.execute("submit_l", {"L_records": [record], "finish": True})
        self.assertEqual(reply.status, "ok", reply.error)
        self.assertEqual(self.loop.state["L_records"]["G204"]["grade"], 3)
        self.assertEqual(
            self.loop.state["L_records"]["G204"]["new_factors"][0]["space_fit_component"], "area"
        )
        await self.loop.tools.execute("submit_draft", {"phase": "draft", "report": {}})
        view = next(f for f in self.loop.done.facts if f.fact_id == fact)
        self.assertEqual(view.provenance_ref, "fact_parents:" + fact)

    async def test_report_keeps_explicit_excluded_candidates(self):
        await self.submit(finish=True)
        reply = await self.loop.tools.execute(
            "submit_draft",
            {
                "phase": "draft",
                "report": {
                    "excluded_candidates": [
                        {
                            "industry_code": "S209",
                            "reasons_segments": [
                                {"type": "text", "text": "자료 한계가 있어 확인 후 검토합니다."}
                            ],
                        }
                    ]
                },
            },
        )
        self.assertEqual(reply.status, "ok", reply.error)
        self.assertEqual([c.industry_code for c in self.loop.done.excluded_candidates], ["S209"])

    async def test_space_directions_infer_components_and_reject_duplicate_direction(self):
        record = await self.observed("I212")
        user_fact = record["factors"][0]["fact_id"]
        with connect(self.path) as db:
            profile = db.execute(
                "SELECT fact_id FROM facts WHERE source='industry_profile' "
                "AND metric='space_requirements' AND industry_code='I212'"
            ).fetchone()[0]
        fact = register_fact(
            self.scope,
            industry_code="I212",
            source="industry_profile",
            metric="space_fit",
            value={
                "floor": "일치",
                "area": "일치",
                "kitchen": "불일치",
                "reviewed": True,
                "confidence": "low",
            },
            unit="공간 비교",
            status="observed",
            row_ids=[],
            parent_fact_ids=[profile, user_fact],
        )
        await self.loop.tools.execute("get_facts", {"fact_ids": [fact]})
        record["factors"] = [
            {"fact_id": fact, "direction": "favorable"},
            {"fact_id": fact, "direction": "favorable"},
        ]
        duplicate = await self.loop.tools.execute("submit_l", {"L_records": [record]})
        self.assertEqual(duplicate.status, "ok", duplicate.error)
        self.assertEqual(duplicate.data.rejected[0]["industry_code"], "I212")
        self.assertEqual(self.loop.state["L_records"], {})
        record["factors"][1]["direction"] = "adverse"
        accepted = await self.loop.tools.execute("submit_l", {"L_records": [record]})
        self.assertEqual(accepted.status, "ok", accepted.error)
        self.assertEqual(self.loop.state["L_records"]["I212"]["grade"], 2)
        self.assertEqual(
            [f["space_fit_component"] for f in self.loop.state["L_records"]["I212"]["new_factors"]],
            ["area", "kitchen"],
        )

    async def test_l_rejects_user_floor_fact(self):
        record = await self.observed("S209", "4층", metric="floor")
        reply = await self.loop.tools.execute("submit_l", {"L_records": [record]})
        self.assertEqual(reply.data.accepted, [])
        self.assertIn("규칙이 채점합니다", reply.data.rejected[0]["reason"])

    async def test_l_rejects_required_facility_space_fit(self):
        record = await self.observed("I201")
        with connect(self.path) as db:
            profile = db.execute(
                "SELECT fact_id FROM facts WHERE source='industry_profile' "
                "AND metric='space_requirements' AND industry_code='I201'"
            ).fetchone()[0]
        fact = register_fact(
            self.scope,
            industry_code="I201",
            source="industry_profile",
            metric="space_fit",
            value={
                "floor": "불일치",
                "ventilation": "불일치",
                "reviewed": True,
                "confidence": "low",
            },
            unit="공간 비교",
            status="observed",
            row_ids=[],
            parent_fact_ids=[profile, record["factors"][0]["fact_id"]],
        )
        await self.loop.tools.execute("get_facts", {"fact_ids": [fact]})
        record["factors"] = [{"fact_id": fact, "direction": "adverse"}]
        reply = await self.loop.tools.execute("submit_l", {"L_records": [record]})
        self.assertEqual(reply.data.accepted, [])
        self.assertEqual(reply.data.rejected[0]["industry_code"], "I201")
