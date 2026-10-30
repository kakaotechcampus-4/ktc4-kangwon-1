"""손님 평가표(K1~K4 코드 채점·K6 모델 점수·판정)는 외부 호출 없이 검증합니다.

정상 초안에 오류를 하나씩 심어 잡는지, 정상 초안에 헛지적하지 않는지를 봅니다.
"""

import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from app.agentic import customer_rubric
from app.agentic.contracts import (
    CustomerCheck,
    FactReferenceSegment,
    FitCheck,
    SubmitDraftInput,
    SubmitLInput,
)
from app.agentic.evaluators import PERSONAS
from app.industries.catalog import INDUSTRIES
from tests import test_agentic_runtime as fixtures

CODES = list(INDUSTRIES)[:5]


def new_id():
    return "f_" + str(uuid.uuid4())


def cite(*ids):
    return [FactReferenceSegment(type="fact", fact_id=i, format="text") for i in ids]


class Site:
    """후보 하나의 D 문항·fact와 초안 문장을 만드는 시험용 묶음입니다."""

    def __init__(self, code, grades, d3_value=None):
        self.code = code
        self.items, self.facts = {}, {}
        for item in customer_rubric.DEMAND:
            grade = grades.get(item)
            if grade == "n.a.":
                self.items[item] = {"status": "n.a.", "grade": None}
            elif grade is None:
                self.items[item] = {"status": "unknown", "grade": None}
            else:
                self.items[item] = {"status": "observed", "grade": grade}
                self.facts[item] = new_id()
        if d3_value is not None:
            self.items["D3"]["value"] = d3_value
        self.reasons, self.risks = [], []

    def candidate(self):
        return SimpleNamespace(
            industry_code=self.code,
            industry_name=INDUSTRIES[self.code],
            reasons_segments=cite(*self.reasons),
            risks_segments=cite(*self.risks),
            confirmation_conditions_segments=[],
        )


def run(sites):
    draft = SimpleNamespace(top5=[s.candidate() for s in sites], score_snapshot_id="ss")
    rows = {s.code: {"code": s.code, "items": s.items} for s in sites}
    item_facts = {(s.code, i): [f] for s in sites for i, f in s.facts.items()}
    citable = {f for s in sites for f in s.facts.values()}
    with patch.object(customer_rubric, "load", return_value=(rows, item_facts, citable)):
        return customer_rubric.code_checks(None, draft)


def checks(scored, rank=1):
    return {c.item: c for c in scored[rank - 1][2]}


class CodeCheckTests(unittest.TestCase):
    def test_clean_draft_has_no_false_issue(self):
        site = Site(CODES[0], {"D1": 3, "D2": 3, "D3": 3, "D4": 2})
        site.reasons = [site.facts["D1"]]
        scored, issues, _ = run([site])
        result = checks(scored)
        self.assertEqual(result["K1"].points, 15)
        self.assertEqual(result["K3"].status, "not_applicable")
        self.assertEqual(result["K4"].status, "not_applicable")
        self.assertEqual(issues, [])

    def test_weak_fact_used_as_reason_and_hidden_from_risk(self):
        site = Site(CODES[0], {"D1": 3, "D2": 3, "D3": 0, "D4": 2})
        site.reasons = [site.facts["D3"]]
        scored, issues, _ = run([site])
        result = checks(scored)
        self.assertEqual(result["K3"].points, 0)
        self.assertEqual(result["K4"].points, 0)
        self.assertEqual(result["K4"].fact_ids, [site.facts["D3"]])
        self.assertEqual(
            sorted(i.issue_id for i in issues),
            [f"customer:reason-{CODES[0]}", f"customer:risk-{CODES[0]}"],
        )

    def test_disclosed_weak_fact_passes(self):
        site = Site(CODES[0], {"D1": 3, "D2": 1, "D3": 3, "D4": 2})
        site.risks = [site.facts["D2"]]
        scored, issues, _ = run([site])
        self.assertEqual(checks(scored)["K3"].points, 15)
        self.assertEqual(checks(scored)["K4"].points, 20)
        self.assertEqual(issues, [])

    def test_population_replacement_is_flagged(self):
        replaced = Site(
            CODES[0],
            {"D1": 3, "D3": 3},
            {"r": 1.1, "population": "유동", "requested_population": "상주"},
        )
        same = Site(
            CODES[1],
            {"D1": 3, "D3": 3},
            {"r": 1.1, "population": "직장", "requested_population": "직장"},
        )
        scored, issues, _ = run([replaced, same])
        self.assertEqual(checks(scored, 1)["K2"].points, 3.3)
        self.assertEqual(checks(scored, 2)["K2"].points, 10)
        self.assertEqual([i.issue_id for i in issues], [f"customer:population-{CODES[0]}"])

    def test_population_points_follow_disclosure(self):
        # 유동 대체 D3 근거를 밝힘 6.7 · 언급 없음 3.3 · 장점에 씀 0(밝혔든 아니든)
        for reason, risk, points in (
            (False, True, 6.7),
            (False, False, 3.3),
            (True, True, 0),
            (True, False, 0),
        ):
            site = Site(
                CODES[0],
                {"D1": 3, "D3": 3},
                {"r": 1.1, "population": "유동", "requested_population": "상주"},
            )
            site.reasons = [site.facts["D3"]] if reason else []
            site.risks = [site.facts["D3"]] if risk else []
            scored, issues, _ = run([site])
            self.assertEqual(checks(scored)["K2"].points, points)
            flagged = f"customer:population-{CODES[0]}" in [i.issue_id for i in issues]
            self.assertEqual(flagged, points < 6)

    def test_partial_misuse_and_disclosure_score_by_ratio(self):
        # 약한 근거 셋 중 하나를 장점에 씀 → K3 15×2/3(지적)
        # 둘 밝힘 → K4 20×2/3(절반 이상이라 지적 없음)
        site = Site(CODES[0], {"D1": 1, "D2": 1, "D3": 1, "D4": 4})
        site.reasons = [site.facts["D1"]]
        site.risks = [site.facts["D1"], site.facts["D2"]]
        scored, issues, _ = run([site])
        self.assertEqual(checks(scored)["K3"].points, 10)
        self.assertEqual(checks(scored)["K4"].points, 13.3)
        self.assertEqual([i.issue_id for i in issues], [f"customer:reason-{CODES[0]}"])

    def test_not_applicable_items_shrink_denominator(self):
        site = Site(CODES[0], {"D1": "n.a.", "D2": "n.a.", "D3": 2, "D4": None})
        scored, _, _ = run([site])
        # 적용 배점 D3·D4 중 D3만 관측 → 비중 2/3 → 15×2/3
        self.assertEqual(checks(scored)["K1"].points, 10)
        self.assertEqual(checks(scored)["K2"].status, "not_applicable")

    def test_issues_are_capped_and_ordered_by_severity(self):
        sites = [Site(code, {}) for code in CODES]
        sites[4] = Site(CODES[4], {"D1": 2, "D3": 0})
        sites[4].reasons = [sites[4].facts["D3"], sites[4].facts["D3"]]
        _, issues, _ = run(sites)
        self.assertEqual(len(issues), 4)
        self.assertEqual(issues[0].issue_id, f"customer:demand-{CODES[0]}")
        self.assertTrue(all(not any(ch.isdigit() for ch in i.comment) for i in issues))


class CustomerCheckTests(unittest.TestCase):
    def test_observed_needs_points_and_points_within_weight(self):
        base = {"item": "K1", "weight": 15, "fact_ids": [], "note": "시험"}
        with self.assertRaises(ValidationError):
            CustomerCheck(status="observed", points=None, **base)
        with self.assertRaises(ValidationError):
            CustomerCheck(status="observed", points=16, **base)
        self.assertEqual(CustomerCheck(status="observed", points=15, **base).points, 15)

    def test_all_demand_items_not_applicable(self):
        site = Site(CODES[0], dict.fromkeys(customer_rubric.DEMAND, "n.a."))
        scored, issues, _ = run([site])
        self.assertEqual(checks(scored)["K1"].status, "not_applicable")
        self.assertEqual(issues, [])


class FinishTests(unittest.TestCase):
    def finish(self, sites, fit=(), model_issues=()):
        scored, issues, citable = run(sites)
        return customer_rubric.finish(scored, issues, list(fit), model_issues, citable)

    def test_agree_with_supported_fit(self):
        site = Site(CODES[0], {"D1": 3, "D2": 3, "D3": 3, "D4": 2})
        check = FitCheck(
            industry_code=CODES[0], points=40, fact_ids=[site.facts["D1"]], reason="근거와 맞음"
        )
        verdict, issues, rubric = self.finish([site], [check])
        self.assertEqual(verdict, "agree")
        self.assertEqual(rubric.candidates[0].checks[-1].points, 40)
        self.assertEqual(rubric.candidates[0].ratio, 1)
        self.assertEqual(issues, [])

    def test_fit_without_citable_evidence_is_unknown(self):
        site = Site(CODES[0], {"D1": 3, "D2": 3, "D3": 3, "D4": 2})
        check = FitCheck(industry_code=CODES[0], points=0, fact_ids=[new_id()], reason="추정")
        _, _, rubric = self.finish([site], [check])
        k6 = rubric.candidates[0].checks[-1]
        self.assertEqual(k6.status, "unknown")
        self.assertIsNone(k6.points)

    def test_no_candidates_is_conditional(self):
        verdict, issues, rubric = customer_rubric.finish([], [], [], [], set())
        self.assertEqual(verdict, "conditional")
        self.assertIsNone(rubric.ratio)
        self.assertEqual(issues, [])

    def test_no_demand_in_top_three_opposes(self):
        verdict, issues, rubric = self.finish([Site(CODES[0], {})], model_issues=None)
        self.assertEqual(verdict, "oppose")
        self.assertEqual(issues[0].fact_ids, [])
        self.assertEqual(rubric.model_status, "failed")

    def test_zero_points_block_agree(self):
        # 약한 근거 둘을 위험에 밝혔지만 장점에도 썼습니다: 득점률은 동의 기준 이상, K3는 0점.
        site = Site(CODES[0], {"D1": 4, "D2": 0, "D3": 0, "D4": 4})
        site.reasons = [site.facts["D2"], site.facts["D3"]]
        site.risks = [site.facts["D2"], site.facts["D3"]]
        verdict, _, rubric = self.finish([site])
        self.assertGreaterEqual(rubric.ratio, customer_rubric.AGREE)
        self.assertEqual(checks([(1, CODES[0], rubric.candidates[0].checks)])["K3"].points, 0)
        self.assertEqual(verdict, "conditional")


class ReviewIntegrationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.RuntimeTests.asyncSetUp
    asyncTearDown = fixtures.RuntimeTests.asyncTearDown
    message = fixtures.RuntimeTests.message

    async def observed_fact(self):
        from app.agentic.facts import register_fact
        from app.db.connection import connect

        response = await self.scope.record(
            source="floating_population",
            source_type="api",
            args={},
            page="test",
            status=200,
            payload={"rows": [{"age": "20", "share": 0.3}]},
        )
        with connect(self.path) as db:
            ref = db.execute(
                "SELECT raw_row_id FROM raw_response_rows WHERE response_id=?", (response,)
            ).fetchone()[0]
        return register_fact(
            self.scope,
            industry_code=None,
            source="floating_population",
            metric="age_share",
            value={"20": 0.3},
            unit="비율",
            status="observed",
            row_ids=[ref],
        )

    async def test_customer_review_merges_model_points_and_limits_slots(self):
        from app.agentic.evaluators import review
        from app.agentic.runtime import DecisionLoop

        fact = await self.observed_fact()
        packets, replies = [], []

        async def evaluator(messages, definitions, settings, receipt):
            payload = json.loads(messages[1]["content"])
            packets.append((payload, definitions))
            tools = [m for m in messages if m["role"] == "tool"]
            if tools:
                replies.append(json.loads(tools[-1]["content"]))
            alias = fact
            issues = (
                []
                if replies
                else [
                    {
                        "issue_id": "motive",
                        "target": "claim",
                        "kind": "missing_evidence",
                        "comment": "추천과 근거가 어긋남",
                        "fact_ids": [alias],
                        "suggested_check": "근거 확인",
                    }
                ]
            )
            return self.message(
                "submit_review",
                {
                    "draft_id": payload["draft_id"],
                    "verdict": "agree",
                    "issues": issues,
                    "fit_checks": [
                        {
                            "industry_code": payload["candidates"][0]["industry_code"],
                            "points": 30,
                            "fact_ids": [alias],
                            "reason": "통행 연령과 대상이 맞음",
                        }
                    ],
                },
            )

        loop = await DecisionLoop.create(self.scope, self.site, evaluator_generate=evaluator)
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        result = await review(loop, "customer", loop.evaluator_executors()["customer"], loop.done)

        payload, definitions = packets[0]
        self.assertNotIn("persona", payload)
        self.assertEqual(payload["remaining_issue_slots"], 0)
        submit = next(d for d in definitions if d["function"]["name"] == "submit_review")
        self.assertIn("fit_checks", submit["function"]["parameters"]["properties"])
        # 코드 지적이 네 칸을 채워 모델 지적은 거절되고 다시 제출됩니다.
        self.assertEqual(replies[0]["error"]["code"], "INVALID_REFERENCE")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.verdict, "oppose")
        self.assertEqual(len(result.issues), 4)
        self.assertTrue(all(i.issue_id.startswith("customer:demand-") for i in result.issues))
        rubric = result.customer_rubric
        k6 = rubric.candidates[0].checks[-1]
        self.assertEqual((k6.points, k6.fact_ids), (30, [fact]))
        self.assertEqual(rubric.model_status, "completed")

    async def test_rejected_submissions_keep_fit_points(self):
        from app.agentic.evaluators import review
        from app.agentic.runtime import DecisionLoop

        fact = await self.observed_fact()
        replies = []

        async def evaluator(messages, definitions, settings, receipt):
            payload = json.loads(messages[1]["content"])
            tools = [m for m in messages if m["role"] == "tool"]
            if tools:
                replies.append(json.loads(tools[-1]["content"]))
            alias = fact
            # 남은 칸이 없는데 숫자 섞인 지적을 계속 내서 제출이 끝까지 거절됩니다.
            return self.message(
                "submit_review",
                {
                    "draft_id": payload["draft_id"],
                    "verdict": "agree",
                    "issues": [
                        {
                            "issue_id": "age",
                            "target": "claim",
                            "kind": "missing_evidence",
                            "comment": "20대 통행만으로는 부족함",
                            "fact_ids": [alias],
                            "suggested_check": "근거 확인",
                        }
                    ],
                    "fit_checks": [
                        {
                            "industry_code": payload["candidates"][0]["industry_code"],
                            "points": 20,
                            "fact_ids": [alias],
                            "reason": "근거가 일반론임",
                        }
                    ],
                },
            )

        loop = await DecisionLoop.create(self.scope, self.site, evaluator_generate=evaluator)
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        result = await review(loop, "customer", loop.evaluator_executors()["customer"], loop.done)

        self.assertIn("남은 칸은", replies[0]["error"]["message"])
        rubric = result.customer_rubric
        self.assertEqual(rubric.model_status, "failed")
        k6 = rubric.candidates[0].checks[-1]
        self.assertEqual((k6.points, k6.fact_ids), (20, [fact]))

    async def test_other_evaluators_do_not_see_fit_field(self):
        from app.agentic.evaluators import review
        from app.agentic.runtime import DecisionLoop

        seen = []

        async def evaluator(messages, definitions, settings, receipt):
            seen.append(definitions)
            payload = json.loads(messages[1]["content"])
            return self.message(
                "submit_review",
                {"draft_id": payload["draft_id"], "verdict": "agree", "issues": []},
            )

        loop = await DecisionLoop.create(self.scope, self.site, evaluator_generate=evaluator)
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        result = await review(loop, "founder", loop.evaluator_executors()["founder"], loop.done)
        self.assertEqual(result.status, "completed")
        self.assertIsNone(result.customer_rubric)
        submit = next(d for d in seen[0] if d["function"]["name"] == "submit_review")
        self.assertNotIn("fit_checks", submit["function"]["parameters"]["properties"])
        self.assertTrue(PERSONAS["customer"])


class RealDbTests(unittest.IsolatedAsyncioTestCase):
    """실제 시험 DB의 점수표로 code_checks·packet·load를 확인합니다."""

    asyncSetUp = fixtures.RuntimeTests.asyncSetUp
    asyncTearDown = fixtures.RuntimeTests.asyncTearDown

    async def draft_loop(self):
        from app.agentic.runtime import DecisionLoop

        loop = await DecisionLoop.create(self.scope, self.site)
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        return loop

    async def test_code_checks_and_packet_follow_top5(self):
        loop = await self.draft_loop()
        draft = loop.done
        scored, issues, _ = customer_rubric.code_checks(loop.scope, draft)
        codes = [c.industry_code for c in draft.top5]
        self.assertEqual(len(scored), len(draft.top5))
        self.assertEqual([code for _, code, _ in scored], codes)
        self.assertEqual([rank for rank, _, _ in scored], list(range(1, len(codes) + 1)))
        for _, _, items in scored:
            self.assertEqual([c.item for c in items], ["K1", "K2", "K3", "K4"])
        packet = customer_rubric.packet(loop.scope, draft, scored, issues)
        self.assertEqual(packet["draft_id"], draft.report_id)
        self.assertEqual([c["industry_code"] for c in packet["candidates"]], codes)
        self.assertEqual(len(packet["code_checks"]), len(codes))
        self.assertEqual(packet["remaining_issue_slots"], 4 - len(issues))

    async def test_load_rejects_missing_score_snapshot(self):
        loop = await self.draft_loop()
        draft = SimpleNamespace(score_snapshot_id="missing", top5=[])
        with self.assertRaises(ValueError):
            customer_rubric.load(loop.scope, draft)


if __name__ == "__main__":
    unittest.main()
