"""임대인 입력의 실제 근거·결측·격리·크기와 역할별 분기를 검증합니다."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.agentic.aliases import decode
from app.agentic.contracts import SubmitDraftInput, SubmitLInput, TextSegment
from app.agentic.evaluators import PERSONAS, review
from app.agentic.facts import register_fact
from app.agentic.landlord import MAX_PACKET_CHARS, review_packet
from app.agentic.runtime import DecisionLoop
from app.canonical import canonical_json
from app.db.connection import connect
from app.db.repository import create_request
from app.storage.raw import capture_scope
from tests import test_agentic_runtime as fixtures


class ContextTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.RuntimeTests.asyncSetUp
    asyncTearDown = fixtures.RuntimeTests.asyncTearDown
    message = fixtures.RuntimeTests.message

    def draft(self, codes=("G215", "I212")):
        return SimpleNamespace(
            report_id="draft",
            limitations_segments=[TextSegment(type="text", text="서울 밖 점포 미반영")],
            top5=[
                SimpleNamespace(
                    industry_code=code,
                    badge="보류",
                    coverage=0.5,
                    demand_coverage=0.5,
                    L_status="unknown",
                )
                for code in codes
            ],
        )

    async def fact(self, code, source, metric, value, *, status="observed", scope=None):
        scope = scope or self.scope
        response = await scope.record(
            source=source,
            source_type="api",
            args={},
            page="1",
            status=200,
            payload={"rows": [{"metric": metric, "value": value}]},
        )
        return await asyncio.to_thread(
            register_fact,
            scope,
            industry_code=code,
            source=source,
            metric=metric,
            value=value,
            status=status,
            unit="시험 단위",
            row_ids=[],
            response_ids=[response],
            period="20233~20262",
            comparison={
                "input_versions": {"spatial_scope": {"radius_m": 500, "area_code": "시험"}}
            },
        )

    async def packet(self, draft=None):
        encoded = await asyncio.to_thread(review_packet, self.scope, draft or self.draft())
        return await asyncio.to_thread(decode, self.scope, encoded)

    async def test_existing_continuity_and_demand_keep_values_period_and_scope(self):
        close = await self.fact("G215", "business_lifecycle", "recent_year_close_rate", 0.12)
        demand = await self.fact("G215", "floating_population", "pattern_fit_index", 1.3)
        packet = await self.packet()
        facts = {f["fact_id"]: f for f in packet["facts"]}
        self.assertEqual(facts[close]["value"], 0.12)
        self.assertEqual(facts[demand]["value"], 1.3)
        self.assertEqual(facts[close]["period"], "20233~20262")
        spatial = packet["spatial_scopes"][facts[close]["spatial_scope_ref"]]
        self.assertEqual(spatial["radius_m"], 500)
        self.assertEqual(packet["limitations_segments"][0]["text"], "서울 밖 점포 미반영")
        self.assertEqual(
            packet["landlord_context"]["evidence"]["G215"]["continuity"]["fact_ids"], [close]
        )
        self.assertTrue(all(f["status"] == "observed" and f["citable"] for f in facts.values()))

    async def test_unknown_and_absent_sources_are_diagnostics_not_citable_facts(self):
        unknown = await self.fact(None, "floating_population", "yoy_change", None, status="unknown")
        observed = await self.fact("G215", "commercial_area", "store_count", 0)
        packet = await self.packet()
        self.assertNotIn(unknown, [f["fact_id"] for f in packet["facts"]])
        self.assertIn(observed, [f["fact_id"] for f in packet["facts"]])
        evidence = packet["landlord_context"]["evidence"]["G215"]
        self.assertGreaterEqual(evidence["demand"]["unknown_count"], 1)
        self.assertEqual(evidence["demand"]["observed_count"], 0)
        self.assertEqual(evidence["continuity"]["observed_count"], 0)
        self.assertEqual(evidence["competition"]["observed_count"], 1)

    async def test_other_request_and_replaced_space_fact_do_not_leak(self):
        create_request("other", "다른 요청", db_path=self.path)
        async with capture_scope("other", self.path) as other:
            foreign = await self.fact(
                "G215", "business_lifecycle", "recent_year_close_rate", 0.9, scope=other
            )
        old = await self.fact("G215", "industry_profile", "space_fit", {"area": "불일치"})
        current = await self.fact("G215", "industry_profile", "space_fit", {"area": "일치"})
        with connect(self.path) as db:
            db.execute(
                "INSERT INTO space_fit_current VALUES(?,?,?,?)",
                (self.scope.request_id, self.scope.snapshot_id, "G215", current),
            )
        packet = await self.packet()
        ids = {f["fact_id"] for f in packet["facts"]}
        self.assertNotIn(foreign, ids)
        self.assertNotIn(old, ids)
        self.assertIn(current, ids)

    async def test_large_space_value_does_not_crowd_out_core_data_for_other_candidates(self):
        codes = ("G215", "G204", "G209", "G215B", "I212")
        for code in codes:
            await self.fact(code, "business_lifecycle", "recent_year_close_rate", 0.1)
            await self.fact(code, "floating_population", "pattern_fit_index", 1.1)
            fid = await self.fact(
                code, "industry_profile", "space_fit", {"area": "일치", "notes": "가" * 10000}
            )
            with connect(self.path) as db:
                db.execute(
                    "INSERT INTO space_fit_current VALUES(?,?,?,?)",
                    (self.scope.request_id, self.scope.snapshot_id, code, fid),
                )
        packet = await self.packet(self.draft(codes))
        self.assertLessEqual(len(canonical_json(packet)), MAX_PACKET_CHARS)
        for code in codes:
            evidence = packet["landlord_context"]["evidence"][code]
            self.assertTrue(evidence["continuity"]["fact_ids"])
            self.assertTrue(evidence["demand"]["fact_ids"])
            self.assertEqual(evidence["space"]["observed_count"], 1)
            self.assertFalse(evidence["space"]["fact_ids"])

    async def test_only_landlord_uses_the_new_packet_builder(self):
        loop = await DecisionLoop.create(self.scope, self.site)
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        draft = loop.done
        packet = {"draft_id": draft.report_id, "facts": []}
        message = self.message(
            "submit_review", {"draft_id": draft.report_id, "verdict": "agree", "issues": []}
        )
        with (
            patch("app.agentic.evaluators.review_packet", return_value=packet) as common,
            patch("app.agentic.landlord.review_packet", return_value=packet) as landlord,
            patch.object(loop, "_model", new=AsyncMock(return_value=(message, {}))),
        ):
            for actor in PERSONAS:
                result = await review(loop, actor, loop.evaluator_executors()[actor], draft)
                self.assertEqual(result.status, "completed")
        self.assertEqual(common.call_count, 3)
        self.assertEqual(landlord.call_count, 1)
