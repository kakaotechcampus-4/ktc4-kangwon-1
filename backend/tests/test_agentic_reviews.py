"""평가자 병렬 실행과 최종 피드백은 외부 호출 없이 검증합니다."""

import asyncio
import json
import sqlite3
import unittest
from unittest.mock import patch

from app.ai.evaluators import PERSONAS
from app.ai.tool_contracts import SubmitDraftInput, SubmitLInput
from app.infrastructure.persistence.connection import connect
from tests import test_agentic_runtime as fixtures
from tests.fact_fixture import fact_record


class ReviewTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.RuntimeTests.asyncSetUp
    asyncTearDown = fixtures.RuntimeTests.asyncTearDown
    message = fixtures.RuntimeTests.message

    async def test_invalid_issue_does_not_discard_valid_issue(self):
        from app.ai.runtime import DecisionLoop

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
        from app.ai.evaluators import review

        with connect(self.scope.path) as db:
            fid = db.execute("SELECT fact_id FROM facts LIMIT 1").fetchone()[0]
        with (
            patch(
                "app.ai.examiner.review_packet",
                return_value={"draft_id": loop.done.report_id, "facts": [{"fact_id": fid}]},
            ),
            patch(
                "app.ai.evaluators.fact_rows",
                return_value={fid: fact_record(fid)},
            ),
        ):
            result = await review(
                loop, "examiner", loop.evaluator_executors()["examiner"], loop.done
            )
        self.assertEqual(result.status, "completed")
        self.assertEqual([i.issue_id for i in result.issues], ["examiner:valid"])
        self.assertEqual(replies[0]["data"]["accepted"], ["valid"])
        self.assertEqual(replies[0]["data"]["rejected"][0]["issue_id"], "invalid")

    async def review_with(self, evaluator=None, *patches):
        from contextlib import ExitStack

        from app.ai.evaluators import review
        from app.ai.runtime import DecisionLoop

        loop = await DecisionLoop.create(self.scope, self.site, evaluator_generate=evaluator)
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "app.ai.examiner.review_packet",
                    return_value={"draft_id": loop.done.report_id, "facts": []},
                )
            )
            for item in patches:
                stack.enter_context(item)
            return await review(loop, "examiner", loop.evaluator_executors()["examiner"], loop.done)

    def submission(self, messages):
        payload = json.loads(messages[1]["content"])
        return self.message(
            "submit_review",
            {"draft_id": payload["draft_id"], "verdict": "agree", "issues": []},
        )

    async def run_scripted_review(self, steps):
        pending = list(steps)
        seen = []

        async def evaluator(messages, definitions, settings, receipt):
            seen.append(
                {
                    "tools": [d["function"]["name"] for d in definitions],
                    "messages": json.loads(json.dumps(messages)),
                }
            )
            if pending:
                raise pending.pop(0)
            return self.submission(messages)

        return await self.review_with(evaluator), seen

    async def run_review_through_client(self, steps):
        from types import SimpleNamespace

        from app.application.ports.llm import llm
        from app.application.ports.llm_settings import LLMSettings
        from app.infrastructure.llm import client

        pending = list(steps)
        attempts = []

        async def request(messages, settings, *, tools, usage, receipt=None):
            attempts.append(1)
            if pending:
                raise pending.pop(0)
            return self.submission(messages)

        async def no_sleep(delay):
            return None

        result = await self.review_with(
            None,
            patch.object(llm, "_value", SimpleNamespace(complete_tools=client.complete_tools)),
            patch.object(client, "_request", request),
            patch.object(client.asyncio, "sleep", no_sleep),
            patch.object(LLMSettings, "require_credentials", lambda self: None),
        )
        return result, attempts

    async def test_timeout_is_retried_once(self):
        from app.application.ports.llm import LLMResponseError

        result, seen = await self.run_scripted_review([LLMResponseError("LLM_TIMEOUT")])
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(seen), 2)

    async def test_http_500_is_retried_once(self):
        from app.application.ports.llm import LLMHTTPError

        result, seen = await self.run_scripted_review([LLMHTTPError(500, {})])
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(seen), 2)

    async def test_second_transient_error_fails(self):
        from app.application.ports.llm import LLMHTTPError, LLMResponseError

        result, seen = await self.run_scripted_review(
            [LLMResponseError("LLM_TIMEOUT"), LLMHTTPError(500, {})]
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "SOURCE_UNAVAILABLE")
        self.assertEqual(len(seen), 2)

    async def test_connection_error_is_left_to_the_client_retry(self):
        from app.application.ports.llm import LLMResponseError

        result, seen = await self.run_scripted_review([LLMResponseError("LLM_CONNECTION_ERROR")])
        self.assertEqual(result.error_code, "SOURCE_UNAVAILABLE")
        self.assertEqual(len(seen), 1)

    async def test_gateway_status_is_left_to_the_client_retry(self):
        from app.application.ports.llm import LLMHTTPError

        result, seen = await self.run_scripted_review([LLMHTTPError(503, {})])
        self.assertEqual(result.error_code, "SOURCE_UNAVAILABLE")
        self.assertEqual(len(seen), 1)

    async def test_credit_exhaustion_is_not_retried(self):
        from app.application.ports.llm import LLMHTTPError

        result, seen = await self.run_scripted_review(
            [LLMHTTPError(429, {"error": {"code": "insufficient_quota"}})]
        )
        self.assertEqual(result.error_code, "SOURCE_UNAVAILABLE")
        self.assertEqual(len(seen), 1)

    async def test_non_transient_error_is_not_retried(self):
        from app.application.ports.llm import LLMResponseError

        result, seen = await self.run_scripted_review([LLMResponseError("LLM_INVALID_JSON")])
        self.assertEqual(result.status, "failed")
        self.assertEqual(len(seen), 1)

    async def test_time_budget_timeout_is_not_retried(self):
        result, seen = await self.run_scripted_review([TimeoutError()])
        self.assertEqual(result.error_code, "TIMEOUT")
        self.assertEqual(len(seen), 1)

    async def test_call_budget_exhaustion_is_not_retried(self):
        from app.application.ports.llm_budget import BudgetExceeded

        result, seen = await self.run_scripted_review([BudgetExceeded()])
        self.assertEqual(result.error_code, "BUDGET_EXCEEDED")
        self.assertEqual(len(seen), 1)

    async def test_retry_resends_same_messages(self):
        from app.application.ports.llm import LLMResponseError

        _, seen = await self.run_scripted_review([LLMResponseError("LLM_TIMEOUT")])
        self.assertEqual(seen[0]["messages"], seen[1]["messages"])

    async def test_truncation_then_timeout_follows_each_rule(self):
        from app.application.ports.llm import LLMResponseError

        result, seen = await self.run_scripted_review(
            [
                LLMResponseError("LLM_OUTPUT_LIMIT", finish_reason="length"),
                LLMResponseError("LLM_TIMEOUT"),
            ]
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(seen), 3)

    async def test_truncation_then_two_timeouts_fail(self):
        from app.application.ports.llm import LLMResponseError

        result, seen = await self.run_scripted_review(
            [
                LLMResponseError("LLM_OUTPUT_LIMIT", finish_reason="length"),
                LLMResponseError("LLM_TIMEOUT"),
                LLMResponseError("LLM_TIMEOUT"),
            ]
        )
        self.assertEqual(result.error_code, "SOURCE_UNAVAILABLE")
        self.assertEqual(len(seen), 3)

    async def test_timeout_does_not_use_up_the_truncation_chances(self):
        from app.application.ports.llm import LLMResponseError

        truncated = LLMResponseError("LLM_OUTPUT_LIMIT", finish_reason="length")
        result, seen = await self.run_scripted_review(
            [LLMResponseError("LLM_TIMEOUT"), truncated, truncated, truncated]
        )
        self.assertEqual(result.error_code, "REPORT_INVALID")
        self.assertEqual(len(seen), 4)

    async def test_client_retries_persistent_connection_error_three_times_then_fails(self):
        from app.application.ports.llm import LLMResponseError

        result, attempts = await self.run_review_through_client(
            [LLMResponseError("LLM_CONNECTION_ERROR")] * 10
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "SOURCE_UNAVAILABLE")
        self.assertEqual(len(attempts), 3)

    async def test_timeout_through_client_is_retried_by_the_evaluator(self):
        from app.application.ports.llm import LLMResponseError

        result, attempts = await self.run_review_through_client([LLMResponseError("LLM_TIMEOUT")])
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(attempts), 2)

    async def test_http_500_through_client_is_retried_by_the_evaluator(self):
        from app.application.ports.llm import LLMHTTPError

        result, attempts = await self.run_review_through_client([LLMHTTPError(500, {})])
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(attempts), 2)

    async def test_truncated_answer_gets_a_shorter_resubmit_chance(self):
        from app.application.ports.llm import LLMResponseError

        result, seen = await self.run_scripted_review(
            [LLMResponseError("LLM_OUTPUT_LIMIT", finish_reason="length")]
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[1]["tools"], ["submit_review"])
        self.assertIn("잘렸", seen[1]["messages"][-1]["content"])

    async def test_three_truncations_end_as_failure(self):
        from app.application.ports.llm import LLMResponseError

        result, seen = await self.run_scripted_review(
            [LLMResponseError("LLM_OUTPUT_LIMIT", finish_reason="length")] * 3
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "REPORT_INVALID")
        self.assertEqual(len(seen), 3)

    async def periods_seen(self, actor):
        from app.ai.evaluators import review
        from app.ai.runtime import DecisionLoop

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
            "examiner": "app.ai.examiner.review_packet",
            "founder": "app.ai.founder.review_packet",
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

    async def test_final_phase_retries_once_at_measured_conversation_size(self):
        from app.ai.runtime import DecisionLoop

        async def evaluator(messages, definitions, settings, receipt):
            payload = json.loads(messages[1]["content"])
            return self.message(
                "submit_review",
                {"draft_id": payload["draft_id"], "verdict": "agree", "issues": []},
            )

        finals = []

        async def decision(messages, definitions, settings, receipt):
            finals.append(messages)
            if len(finals) == 1:
                return self.message("get_facts", {"limit": 1})
            reviews = next(
                json.loads(m["content"])["reviews"]
                for m in reversed(messages)
                if m["role"] == "user" and '"reviews"' in m["content"]
            )
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
        loop.state["messages"].append({"role": "user", "content": "x" * 50000})
        outcome = await loop.review_and_finalize()
        self.assertEqual(len(finals), 2)
        instruction = next(
            json.loads(m["content"])["instruction"]
            for m in finals[0]
            if m["role"] == "user" and '"reviews"' in m["content"]
        )
        for rule in ("applied", "not_applied", "fact_ids", "format", "빈 text"):
            self.assertIn(rule, instruction)
        texts = [s.text for s in outcome.result.limitations_segments if s.type == "text"]
        self.assertNotIn("피드백 최종 반영을 완료하지 못했습니다.", texts)
        self.assertNotIn("호출·시간·토큰 예산 상한에 도달해 코드 점수로 마무리했습니다.", texts)

    async def test_parallel_reviews_keep_failure_slot_and_finalize_once(self):
        from app.ai.runtime import DecisionLoop

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
