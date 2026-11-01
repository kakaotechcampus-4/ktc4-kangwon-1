"""손님 평가자의 제출 거절 규칙과 모델 실패 처리를 외부 호출 없이 검증합니다."""

import json
import unittest
from unittest.mock import patch

from app.agentic.contracts import ReviewIssue, SubmitDraftInput, SubmitLInput
from app.agentic.evaluators import review
from app.db.connection import connect
from tests import test_agentic_runtime as fixtures


class CustomerSubmitTests(unittest.IsolatedAsyncioTestCase):
    asyncTearDown = fixtures.RuntimeTests.asyncTearDown
    message = fixtures.RuntimeTests.message

    async def asyncSetUp(self):
        await fixtures.RuntimeTests.asyncSetUp(self)
        with connect(self.scope.path) as db:
            self.fid = db.execute("SELECT fact_id FROM facts LIMIT 1").fetchone()[0]

    def issue(self, issue_id, comment="손님 동선 확인", **extra):
        return {
            "issue_id": issue_id,
            "target": "condition",
            "kind": "action_condition",
            "comment": comment,
            "fact_ids": [self.fid],
            "suggested_check": "현장 확인",
        } | extra

    def code_issue(self):
        return ReviewIssue(
            issue_id="customer:demand-code",
            target="score",
            kind="missing_evidence",
            comment="코드 지적",
            fact_ids=[],
            suggested_check="확인",
        )

    async def run_review(
        self, submissions, citable=True, code_issues=(), actor="customer", fail=None
    ):
        """submissions를 차례로 제출하고 (결과, 제출별 도구 응답, 도구 정의)를 돌려줍니다."""
        from app.agentic.runtime import DecisionLoop

        replies, seen, queue = [], [], list(submissions)

        async def evaluator(messages, definitions, settings, receipt):
            payload = json.loads(messages[1]["content"])
            if len(messages) == 2:
                seen.append(definitions)
            else:
                replies.append(
                    json.loads(
                        next(m["content"] for m in reversed(messages) if m["role"] == "tool")
                    )
                )
            if fail:
                raise fail
            issues = queue.pop(0) if queue else []
            return self.message(
                "submit_review",
                {"draft_id": payload["draft_id"], "verdict": "conditional", "issues": issues},
            )

        loop = await DecisionLoop.create(self.scope, self.site, evaluator_generate=evaluator)
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        packet = {"draft_id": loop.done.report_id, "facts": [{"fact_id": self.fid}]}
        rows = {self.fid: {"citable": citable, "status": "observed"}}
        with (
            patch(
                "app.agentic.customer_rubric.code_checks",
                return_value=([], list(code_issues), set()),
            ),
            patch("app.agentic.customer_rubric.packet", return_value=packet),
            patch("app.agentic.evaluators.review_packet", return_value=packet),
            patch("app.agentic.evaluators.fact_rows", return_value=rows),
        ):
            result = await review(loop, actor, loop.evaluator_executors()[actor], loop.done)
        return result, replies, seen[0] if seen else []

    async def test_duplicate_issue_id_is_rejected_then_corrected(self):
        dup = self.issue("dup")
        result, replies, _ = await self.run_review([[dup, dup], [dup]])
        self.assertEqual(replies[0]["error"]["code"], "INVALID_REFERENCE")
        self.assertIn("다른 issue_id", replies[0]["error"]["message"])
        self.assertEqual(result.status, "completed")
        self.assertEqual([i.issue_id for i in result.issues], ["customer:dup"])

    async def test_limit_is_four_minus_code_issues(self):
        # 코드 지적이 한 칸을 쓰므로 모델 지적 네 개는 거절됩니다.
        four = [self.issue(i) for i in "abcd"]
        result, replies, _ = await self.run_review(
            [four, four[:3]], code_issues=[self.code_issue()]
        )
        self.assertIn("남은 칸", replies[0]["error"]["message"])
        self.assertEqual(
            [i.issue_id for i in result.issues],
            ["customer:demand-code", "customer:a", "customer:b", "customer:c"],
        )

    async def test_digit_in_comment_rejects_only_that_issue(self):
        bad = self.issue("digit", comment="20대 손님 많음")
        _, replies, _ = await self.run_review([[self.issue("ok"), bad]])
        self.assertEqual(replies[0]["data"]["accepted"], ["ok"])
        rejected = replies[0]["data"]["rejected"]
        self.assertEqual([r["issue_id"] for r in rejected], ["digit"])
        self.assertIn("연령대·층수 포함", rejected[0]["reason"])

    async def test_uncitable_fact_is_rejected(self):
        _, replies, _ = await self.run_review([[self.issue("x")]], citable=False)
        self.assertEqual(replies[0]["data"]["accepted"], [])
        self.assertIn("관측", replies[0]["data"]["rejected"][0]["reason"])

    async def assert_model_failed(self, **kwargs):
        result, _, _ = await self.run_review(code_issues=[self.code_issue()], **kwargs)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.customer_rubric.model_status, "failed")
        self.assertEqual([i.issue_id for i in result.issues], ["customer:demand-code"])

    async def test_three_failed_submissions_keep_code_issues(self):
        await self.assert_model_failed(submissions=[[self.issue("bad", fact_ids=[])]] * 3)

    async def test_timeout_keeps_code_issues(self):
        await self.assert_model_failed(submissions=[], fail=TimeoutError())

    async def test_accepted_issue_ids_are_prefixed(self):
        result, _, _ = await self.run_review([[self.issue("ok")]])
        self.assertEqual([i.issue_id for i in result.issues], ["customer:ok"])
        self.assertEqual(result.customer_rubric.model_status, "completed")

    def properties(self, definitions):
        submit = next(d for d in definitions if d["function"]["name"] == "submit_review")
        return submit["function"]["parameters"]["properties"]

    async def test_customer_definition_has_fit_checks(self):
        _, _, definitions = await self.run_review([[]])
        self.assertIn("fit_checks", self.properties(definitions))

    async def test_other_actor_definition_has_no_fit_checks(self):
        _, _, definitions = await self.run_review([[]], actor="founder")
        self.assertNotIn("fit_checks", self.properties(definitions))


if __name__ == "__main__":
    unittest.main()
