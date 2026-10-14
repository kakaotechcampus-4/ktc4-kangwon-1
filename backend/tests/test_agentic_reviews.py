"""평가자 병렬 실행과 최종 피드백은 외부 호출 없이 검증합니다."""

import asyncio
import json
import unittest

from app.agentic.contracts import SubmitDraftInput
from tests import test_agentic_runtime as fixtures


class ReviewTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.RuntimeTests.asyncSetUp
    asyncTearDown = fixtures.RuntimeTests.asyncTearDown
    message = fixtures.RuntimeTests.message

    async def test_parallel_reviews_keep_failure_slot_and_finalize_once(self):
        from app.agentic.runtime import DecisionLoop

        entered = set()
        ready = asyncio.Event()
        finals = []

        async def evaluator(messages, definitions, settings, receipt):
            payload = json.loads(messages[1]["content"])
            actor = payload["actor"]
            entered.add(actor)
            if len(entered) == 4:
                ready.set()
            await asyncio.wait_for(ready.wait(), 2)
            if actor == "customer":
                raise TimeoutError()
            return self.message(
                "submit_review",
                {"draft_id": payload["draft"]["report_id"], "verdict": "agree", "issues": []},
            )

        async def decision(messages, definitions, settings, receipt):
            finals.append(messages)
            return self.message(
                "submit_draft", {"phase": "final", "report": {}, "review_resolutions": []}
            )

        loop = await DecisionLoop.create(
            self.scope, self.site, generate=decision, evaluator_generate=evaluator
        )
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        outcome = await loop.review_and_finalize()
        self.assertEqual(outcome.status, "completed")
        self.assertEqual(len(outcome.result.evaluator_reviews), 4)
        self.assertEqual(outcome.result.review_completeness, 0.75)
        self.assertEqual(len(finals), 1)
        self.assertEqual(loop.state["feedback_rounds"], 1)
        self.assertEqual(len(entered), 4)
