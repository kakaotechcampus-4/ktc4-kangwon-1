"""평가자 병렬 실행과 최종 피드백은 외부 호출 없이 검증합니다."""

import asyncio
import json
import unittest
from unittest.mock import patch

from app.agentic.contracts import SubmitDraftInput, SubmitLInput
from app.agentic.evaluators import PERSONAS
from app.db.connection import connect
from tests import test_agentic_runtime as fixtures


def resolve_all(messages):
    """최종 단계 메시지의 모든 평가 지적을 반영 처리하는 가짜 decision 응답입니다."""
    reviews = json.loads(messages[-1]["content"]).get("reviews", [])
    return [
        {"issue_id": issue["issue_id"], "disposition": "accepted", "reason": "반영"}
        for review in reviews
        for issue in review["issues"]
    ]


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
                "app.agentic.evaluators.review_packet",
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
            if actor == "customer":
                raise TimeoutError()
            return self.message(
                "submit_review",
                {"draft_id": payload["draft_id"], "verdict": "agree", "issues": []},
            )

        async def decision(messages, definitions, settings, receipt):
            finals.append(messages)
            return self.message(
                "submit_draft",
                {"phase": "final", "report": {}, "review_resolutions": resolve_all(messages)},
            )

        loop = await DecisionLoop.create(
            self.scope, self.site, generate=decision, evaluator_generate=evaluator
        )
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        outcome = await loop.review_and_finalize()
        self.assertEqual(outcome.status, "completed")
        self.assertEqual(len(outcome.result.evaluator_reviews), 4)
        # 손님 모델 실패는 코드 채점(K1~K4)으로 완료하고 모델 상태만 실패로 남깁니다.
        self.assertEqual(outcome.result.review_completeness, 1)
        customer = next(r for r in outcome.result.evaluator_reviews if r.actor == "customer")
        self.assertEqual(customer.customer_rubric.model_status, "failed")
        self.assertEqual(len(finals), 1)
        self.assertEqual(loop.state["feedback_rounds"], 1)
        self.assertEqual(len(entered), 4)
