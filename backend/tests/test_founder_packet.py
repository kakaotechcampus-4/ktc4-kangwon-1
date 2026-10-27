"""임차인 패킷의 본문·운영 근거·크기·제출 경계를 검증합니다."""

import asyncio
import unittest
from types import SimpleNamespace

from app.agentic import evaluators
from app.agentic.aliases import decode
from app.agentic.contracts import (
    FactReferenceSegment,
    ReviewIssue,
    SubmitDraftInput,
    SubmitLInput,
    TextSegment,
)
from app.agentic.report import ReportInvalid
from app.agentic.runtime import DecisionLoop
from app.canonical import canonical_json
from app.db.connection import connect
from app.db.repository import create_request
from app.storage.raw import capture_scope
from tests import test_agentic_runtime as fixtures
from tests import test_landlord_context as context_fixtures


class FounderPacketTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.RuntimeTests.asyncSetUp
    asyncTearDown = fixtures.RuntimeTests.asyncTearDown
    message = fixtures.RuntimeTests.message
    fact = context_fixtures.ContextTests.fact

    async def draft(self):
        loop = await DecisionLoop.create(self.scope, self.site)
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        for candidate in loop.done.top5:
            candidate.reasons_segments = [
                TextSegment(type="text", text="작업 공간을 확보할 수 있습니다.")
            ]
            candidate.risks_segments = [
                TextSegment(type="text", text="공사 허용 범위 확인이 필요합니다.")
            ]
            candidate.confirmation_conditions_segments = [
                TextSegment(type="text", text="반입 동선과 작업 배치를 확인하세요.")
            ]
        return loop, loop.done

    async def packet(self, draft):
        from app.agentic import founder

        return await asyncio.to_thread(founder.review_packet, self.scope, draft)

    async def test_five_candidate_sentences_and_continuity_competition_are_supplied(self):
        _, draft = await self.draft()
        expected = {}
        for candidate in draft.top5:
            code = candidate.industry_code
            expected[code] = [
                await self.fact(code, "business_lifecycle", "recent_year_close_rate", 0.12),
                await self.fact(code, "commercial_area", "store_count", 0),
            ]
        packet = await self.packet(draft)
        self.assertEqual(len(packet["candidates"]), 5)
        self.assertLessEqual(len(canonical_json(packet)), 12000)
        for fact in packet["facts"]:
            self.assertRegex(fact["fact_id"], r"^[a-f0-9]{8}$")
        decoded = await asyncio.to_thread(decode, self.scope, packet)
        facts = {f["fact_id"]: f for f in decoded["facts"]}
        for candidate in decoded["candidates"]:
            self.assertEqual(
                candidate["reasons_segments"][0]["text"], "작업 공간을 확보할 수 있습니다."
            )
            self.assertEqual(
                candidate["risks_segments"][0]["text"], "공사 허용 범위 확인이 필요합니다."
            )
            self.assertEqual(
                candidate["confirmation_conditions_segments"][0]["text"],
                "반입 동선과 작업 배치를 확인하세요.",
            )
            close, count = expected[candidate["industry_code"]]
            self.assertEqual(facts[close]["value"], 0.12)
            self.assertEqual(facts[count]["value"], 0)
            self.assertEqual(facts[close]["period"], "20233~20262")

    async def test_large_values_and_missing_sources_do_not_remove_sentences(self):
        _, draft = await self.draft()
        code = draft.top5[0].industry_code
        fid = await self.fact(
            code, "business_lifecycle", "recent_year_close_rate", {"notes": "가" * 15000}
        )
        unknown = await self.fact(code, "commercial_area", "store_count", None, status="unknown")
        draft.top5[0].reasons_segments.append(
            FactReferenceSegment(type="fact", fact_id=fid, format="text")
        )
        packet = await self.packet(draft)
        self.assertLessEqual(len(canonical_json(packet)), 12000)
        decoded = await asyncio.to_thread(decode, self.scope, packet)
        self.assertEqual(decoded["candidates"][0]["reasons_segments"][-1]["fact_id"], fid)
        self.assertNotIn(unknown, [f["fact_id"] for f in decoded["facts"]])
        card = next(f for f in decoded["facts"] if f["fact_id"] == fid)
        self.assertTrue(card["read_required"])
        self.assertNotIn("value", card)

    async def test_confirmed_values_keep_states_and_other_request_is_not_read(self):
        from app.agentic.questions import save_confirmed_space

        _, draft = await self.draft()
        values = {
            "floor": "1층",
            "exclusive_area": "약 40㎡",
            "existing_facilities": {
                "kitchen": "installable",
                "ventilation": "unavailable",
                "water_supply": "present",
            },
        }
        await asyncio.to_thread(save_confirmed_space, self.scope, values)
        create_request("other", "다른 주소", db_path=self.path)
        async with capture_scope("other", self.path) as other:
            foreign = await self.fact(None, "user", "floor", "지하", scope=other)
        encoded = await self.packet(draft)
        decoded = await asyncio.to_thread(decode, self.scope, encoded)
        facts = decoded["facts"]
        self.assertNotIn(foreign, [f["fact_id"] for f in facts])
        observed = {f["metric"]: f["value"] for f in facts if f["source"] == "user"}
        self.assertEqual(observed, values)

    async def test_oversized_sentences_fail_without_truncation(self):
        _, draft = await self.draft()
        payload = draft.model_dump(mode="json")
        payload["top5"][0]["reasons_segments"] = [{"type": "text", "text": "가" * 13000}]
        oversized = SimpleNamespace(model_dump=lambda **kwargs: payload)
        with self.assertRaises(ValueError):
            await self.packet(oversized)

    async def test_card_omission_keeps_sentence_alias_and_current_space_only(self):
        _, draft = await self.draft()
        code = draft.top5[0].industry_code
        old = await self.fact(code, "industry_profile", "space_fit", {"area": "불일치"})
        current = await self.fact(code, "industry_profile", "space_fit", {"area": "일치"})
        with connect(self.path) as db:
            db.execute(
                "INSERT INTO space_fit_current VALUES(?,?,?,?) "
                "ON CONFLICT(request_id,snapshot_id,industry_code) "
                "DO UPDATE SET fact_id=excluded.fact_id",
                (self.scope.request_id, self.scope.snapshot_id, code, current),
            )
        for index in range(70):
            await self.fact(code, "commercial_area", "store_count", index)
        packet = await self.packet(draft)
        self.assertLessEqual(len(canonical_json(packet)), 12000)
        self.assertTrue(packet["omitted_fact_ids"])
        decoded = await asyncio.to_thread(decode, self.scope, packet)
        self.assertEqual(decoded["evidence"][code]["space"]["fact_ids"], [current])
        self.assertNotIn(old, [f["fact_id"] for f in decoded["facts"]])
        self.assertEqual(
            next(f["value"] for f in decoded["facts"] if f["fact_id"] == current),
            {"area": "일치"},
        )
        for candidate in decoded["candidates"]:
            self.assertEqual(len(candidate["reasons_segments"]), 1)
            self.assertEqual(len(candidate["risks_segments"]), 1)
            self.assertEqual(len(candidate["confirmation_conditions_segments"]), 1)

    async def test_founder_rejects_rescoring_and_can_resubmit_action_condition(self):
        loop, draft = await self.draft()
        await self.fact(None, "user", "space_condition", "공사 범위 확인 필요")
        received = []

        async def generate(messages, definitions, settings, receipt):
            import json

            packet = json.loads(messages[1]["content"])
            alias = next(f["fact_id"] for f in packet["facts"] if f["metric"] == "space_condition")
            received.append(messages)
            return self.message(
                "submit_review",
                {
                    "draft_id": draft.report_id,
                    "verdict": "conditional",
                    "issues": [
                        {
                            "issue_id": "operation",
                            "industry_code": draft.top5[0].industry_code,
                            "target": "score" if len(received) == 1 else "condition",
                            "kind": "duplicate_score" if len(received) == 1 else "action_condition",
                            "comment": "공사 책임 확인이 필요합니다.",
                            "suggested_check": "공사 허용 범위를 협의하세요.",
                            "fact_ids": [alias],
                        }
                    ],
                },
            )

        loop.evaluator_generate = generate
        result = await evaluators.review(
            loop, "founder", loop.evaluator_executors()["founder"], draft
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(received), 2)
        self.assertEqual([i.target for i in result.issues], ["condition"])

    async def test_review_routes_founder_packet_and_accepts_grounded_operating_claim(self):
        seen = []
        loop, draft = await self.draft()
        fid = await self.fact(None, "user", "space_condition", "공사 허용 범위 확인 필요")

        async def generate(messages, definitions, settings, receipt):
            import json

            packet = json.loads(messages[1]["content"])
            seen.append(packet)
            alias = next(f["fact_id"] for f in packet["facts"] if f["metric"] == "space_condition")
            return self.message(
                "submit_review",
                {
                    "draft_id": draft.report_id,
                    "verdict": "conditional",
                    "issues": [
                        {
                            "issue_id": "construction",
                            "industry_code": draft.top5[0].industry_code,
                            "target": "claim",
                            "kind": "factual_error",
                            "fact_ids": [alias],
                            "comment": "공사 허용 확인 전에 작업 공간 확보를 단정했습니다.",
                            "suggested_check": "공사 허용 범위를 확인 조건으로 남기세요.",
                        }
                    ],
                },
            )

        # 외부 모델만 대체하고 실제 패킷·도구·제출 검증을 통과시킵니다.
        loop.evaluator_generate = generate
        result = await evaluators.review(
            loop, "founder", loop.evaluator_executors()["founder"], draft
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.issues[0].fact_ids, [fid])
        self.assertEqual(len(seen[0]["candidates"]), 5)


class FounderIssueTests(unittest.TestCase):
    def test_overflow_removes_competition_then_continuity_and_preserves_space(self):
        from app.agentic.founder import _trim_packet

        for padding, removed in ((8500, {"competition"}), (10000, {"competition", "continuity"})):
            with self.subTest(padding=padding):
                packet = {
                    "candidates": [
                        {"reasons_segments": [{"type": "text", "text": "가" * padding}]}
                    ],
                    "facts": [
                        {
                            "fact_id": "competition",
                            "source": "commercial_area",
                            "metric": "competition_index",
                            "value": "나" * 1500,
                        },
                        {
                            "fact_id": "continuity",
                            "source": "business_lifecycle",
                            "metric": "recent_year_close_rate",
                            "value": "다" * 1500,
                        },
                        {
                            "fact_id": "space",
                            "source": "industry_profile",
                            "metric": "space_fit",
                            "value": {"area": "일치", "notes": "라" * 700},
                        },
                    ],
                }
                _trim_packet(packet)
                self.assertLessEqual(len(canonical_json(packet)), 12000)
                self.assertEqual(
                    {f["fact_id"] for f in packet["facts"] if f.get("read_required")}
                    | set(packet["omitted_fact_ids"]),
                    removed,
                )
                self.assertEqual(
                    next(f for f in packet["facts"] if f["fact_id"] == "space")["value"]["area"],
                    "일치",
                )
                self.assertEqual(
                    packet["candidates"][0]["reasons_segments"][0]["text"], "가" * padding
                )
                self.assertEqual(
                    {f["fact_id"] for f in packet["facts"]} | set(packet["omitted_fact_ids"]),
                    {"space", "continuity", "competition"},
                )

    def test_only_visible_claims_or_action_conditions_are_allowed(self):
        from app.agentic.founder import validate_issue

        packet = {
            "candidates": [
                {
                    "industry_code": "G203",
                    "reasons_segments": [{"type": "text", "text": "운영 가능"}],
                }
            ]
        }
        issue = ReviewIssue(
            issue_id="check",
            industry_code="G203",
            target="claim",
            kind="factual_error",
            comment="운영 단정",
            suggested_check="공사 확인",
        )
        validate_issue(issue, packet)
        for changes in (
            {"industry_code": "I201"},
            {"target": "score", "kind": "duplicate_score"},
            {"target": "fact", "kind": "scope_mismatch"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ReportInvalid):
                validate_issue(issue.model_copy(update=changes), packet)
        with self.assertRaises(ReportInvalid):
            validate_issue(issue, {"candidates": [{"industry_code": "G203"}]})
        validate_issue(
            issue.model_copy(update={"target": "condition", "kind": "action_condition"}), packet
        )
