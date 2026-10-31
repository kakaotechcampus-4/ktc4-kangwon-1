"""평가자 병렬 실행과 최종 피드백은 외부 호출 없이 검증합니다."""

import asyncio
import json
import sqlite3
import unittest
from unittest.mock import patch

from app.agentic.contracts import SubmitDraftInput, SubmitLInput
from app.agentic.evaluators import PERSONAS
from app.db.connection import connect
from tests import test_agentic_runtime as fixtures


class ReviewTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.RuntimeTests.asyncSetUp
    asyncTearDown = fixtures.RuntimeTests.asyncTearDown
    message = fixtures.RuntimeTests.message

    async def test_invalid_issue_does_not_discard_valid_issue(self):
        from app.agentic.runtime import DecisionLoop

        replies = []

        async def evaluator(messages, definitions, settings, receipt):
            payload = json.loads(messages[1]["content"])
            if len(messages) == 2:
                fact = payload["facts"][0]["fact_id"]
                return self.message(
                    "submit_review",
                    {
                        "draft_id": payload["draft_id"],
                        "verdict": "conditional",
                        "issues": [
                            {
                                "issue_id": "valid",
                                "target": "condition",
                                "kind": "action_condition",
                                "comment": "R104 조건 확인",
                                "fact_ids": [fact],
                                "suggested_check": "운영 조건 확인",
                            },
                            {
                                "issue_id": "invalid",
                                "target": "condition",
                                "kind": "missing_evidence",
                                "comment": "근거 확인",
                                "fact_ids": [],
                                "suggested_check": "원문 확인",
                            },
                        ],
                    },
                )
            replies.append(
                json.loads(next(m["content"] for m in reversed(messages) if m["role"] == "tool"))
            )
            return self.message(
                "submit_review",
                {"draft_id": payload["draft_id"], "verdict": "conditional", "issues": []},
            )

        loop = await DecisionLoop.create(self.scope, self.site, evaluator_generate=evaluator)
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        from app.agentic.evaluators import review

        with connect(self.scope.path) as db:
            fid = db.execute("SELECT fact_id FROM facts LIMIT 1").fetchone()[0]
        with (
            patch(
                "app.agentic.examiner.review_packet",
                return_value={"draft_id": loop.done.report_id, "facts": [{"fact_id": fid}]},
            ),
            patch(
                "app.agentic.evaluators.fact_rows",
                return_value={fid: {"citable": True, "status": "observed"}},
            ),
        ):
            result = await review(
                loop, "examiner", loop.evaluator_executors()["examiner"], loop.done
            )
        self.assertEqual(result.status, "completed")
        self.assertEqual([i.issue_id for i in result.issues], ["examiner:valid"])
        self.assertEqual(replies[0]["data"]["accepted"], ["valid"])
        self.assertEqual(replies[0]["data"]["rejected"][0]["issue_id"], "invalid")

    async def run_truncated_review(self, truncations):
        from app.agentic.evaluators import review
        from app.agentic.runtime import DecisionLoop
        from app.llm.client import LLMResponseError

        seen = []

        async def evaluator(messages, definitions, settings, receipt):
            seen.append(
                (
                    [d["function"]["name"] for d in definitions],
                    messages[-1]["content"] if messages[-1]["role"] == "user" else "",
                )
            )
            if len(seen) <= truncations:
                raise LLMResponseError("LLM_OUTPUT_LIMIT", finish_reason="length")
            payload = json.loads(messages[1]["content"])
            return self.message(
                "submit_review",
                {"draft_id": payload["draft_id"], "verdict": "agree", "issues": []},
            )

        loop = await DecisionLoop.create(self.scope, self.site, evaluator_generate=evaluator)
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        with patch(
            "app.agentic.examiner.review_packet",
            return_value={"draft_id": loop.done.report_id, "facts": []},
        ):
            result = await review(
                loop, "examiner", loop.evaluator_executors()["examiner"], loop.done
            )
        return result, seen

    async def test_truncated_answer_gets_a_shorter_resubmit_chance(self):
        result, seen = await self.run_truncated_review(truncations=1)
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[1][0], ["submit_review"])
        self.assertIn("잘렸", seen[1][1])

    async def test_three_truncations_end_as_failure(self):
        result, seen = await self.run_truncated_review(truncations=3)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "REPORT_INVALID")
        self.assertEqual(len(seen), 3)

    async def periods_seen(self, actor):
        from app.agentic.evaluators import review
        from app.agentic.runtime import DecisionLoop

        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            with db:
                row = dict(db.execute("SELECT * FROM facts LIMIT 1").fetchone())
                row.update(
                    fact_id="f_00000000-0000-4000-8000-0000000000aa",
                    identity_hash="period-check",
                    period="20231~20234",
                    status="observed",
                    citable=1,
                    value_json="1.5",
                )
                db.execute(
                    f"INSERT INTO facts({','.join(row)}) VALUES({','.join('?' * len(row))})",
                    list(row.values()),
                )
        finally:
            db.close()
        seen = []

        async def evaluator(messages, definitions, settings, receipt):
            seen.append(messages)
            payload = json.loads(messages[1]["content"])
            if len(seen) == 1:
                return self.message("get_facts", {"fact_ids": [payload["facts"][0]["fact_id"]]})
            return self.message(
                "submit_review",
                {"draft_id": payload["draft_id"], "verdict": "agree", "issues": []},
            )

        loop = await DecisionLoop.create(self.scope, self.site, evaluator_generate=evaluator)
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        packet = {
            "draft_id": loop.done.report_id,
            "facts": [
                {"fact_id": "f_00000000-0000-4000-8000-0000000000aa", "period": "20231~20234"}
            ],
        }
        target = {
            "examiner": "app.agentic.examiner.review_packet",
            "founder": "app.agentic.founder.review_packet",
        }[actor]
        with patch(target, return_value=packet):
            await review(loop, actor, loop.evaluator_executors()[actor], loop.done)
        first = json.loads(seen[0][1]["content"])["facts"][0]["period"]
        reply = next(m["content"] for m in reversed(seen[1]) if m["role"] == "tool")
        return first, reply

    async def test_examiner_sees_spelled_out_periods(self):
        first, reply = await self.periods_seen("examiner")
        self.assertEqual(first, "2023년 1분기~4분기")
        self.assertIn("2023년 1분기~4분기", reply)

    async def test_other_evaluators_keep_period_codes(self):
        first, reply = await self.periods_seen("founder")
        self.assertEqual(first, "20231~20234")
        self.assertIn("20231~20234", reply)
        self.assertNotIn("2023년", reply)

    async def test_parallel_reviews_keep_failure_slot_and_finalize_once(self):
        from app.agentic.runtime import DecisionLoop

        entered = set()
        ready = asyncio.Event()
        finals = []

        async def evaluator(messages, definitions, settings, receipt):
            payload = json.loads(messages[1]["content"])
            actor = next(
                actor
                for actor, persona in PERSONAS.items()
                if messages[0]["content"].startswith(persona)
            )
            entered.add(actor)
            if len(entered) == 4:
                ready.set()
            await asyncio.wait_for(ready.wait(), 2)
            # 손님 평가자는 모델이 실패해도 완료로 남으므로 창업자로 실패 칸을 만듭니다.
            if actor == "founder":
                raise TimeoutError()
            return self.message(
                "submit_review",
                {"draft_id": payload["draft_id"], "verdict": "agree", "issues": []},
            )

        async def decision(messages, definitions, settings, receipt):
            finals.append(messages)
            # 손님 평가자의 코드 지적도 모두 수용 처리해야 최종 제출이 통과합니다.
            reviews = json.loads(messages[-1]["content"])["reviews"]
            resolutions = [
                {"issue_id": i["issue_id"], "disposition": "accepted", "reason": "반영"}
                for r in reviews
                for i in r["issues"]
            ]
            return self.message(
                "submit_draft",
                {"phase": "final", "report": {}, "review_resolutions": resolutions},
            )

        loop = await DecisionLoop.create(
            self.scope, self.site, generate=decision, evaluator_generate=evaluator
        )
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        outcome = await loop.review_and_finalize()
        self.assertEqual(outcome.status, "completed")
        self.assertEqual(len(outcome.result.evaluator_reviews), 4)
        self.assertEqual(outcome.result.review_completeness, 0.75)
        self.assertEqual(len(finals), 1)
        self.assertEqual(loop.state["feedback_rounds"], 1)
        self.assertEqual(len(entered), 4)
