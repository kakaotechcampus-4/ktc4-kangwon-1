"""재개 후 실패와 질문 권한·병렬 취소 경계를 검증합니다."""

import json
import unittest

from app.db.connection import connect
from tests import test_agentic_runtime as fixtures


class CleanupRuntimeTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.RuntimeTests.asyncSetUp
    asyncTearDown = fixtures.RuntimeTests.asyncTearDown
    message = fixtures.RuntimeTests.message

    async def test_resume_value_error_is_saved_failed(self):
        from app.services.agentic_analysis import execute_agentic_analysis, resume_agentic_analysis

        async def resolve(address):
            return self.site

        async def ask(*args):
            return self.message(
                "ask_user",
                {"questions": [{"field": "floor", "question": "층은?", "reason": "조건 확인"}]},
            )

        async def fail(*args):
            raise ValueError("재개 대역 실패")

        waiting = await execute_agentic_analysis(
            "시험",
            db_path=self.path,
            request_id="resume-fail",
            mock=True,
            resolve=resolve,
            generate=ask,
            allow_questions=True,
        )
        self.assertEqual(waiting.status, "waiting_for_input")
        with self.assertRaises(ValueError):
            await resume_agentic_analysis(
                "resume-fail", {"floor": "지상"}, db_path=self.path, generate=fail
            )
        with connect(self.path) as db:
            self.assertEqual(
                db.execute(
                    "SELECT status FROM analysis_requests WHERE request_id='resume-fail'"
                ).fetchone()[0],
                "failed",
            )
            detail = json.loads(
                db.execute(
                    "SELECT diagnostics_json FROM decision_failures WHERE request_id='resume-fail'"
                ).fetchone()[0]
            )
            self.assertEqual(detail[0]["exception_class"], "ValueError")

    async def test_question_definition_and_execution_are_both_disabled(self):
        from app.agents.agentic.runtime import DecisionLoop

        loop = await DecisionLoop.create(self.scope, self.site, allow_questions=False)
        self.assertNotIn("ask_user", [d["function"]["name"] for d in loop.definitions()])
        reply = await loop.tools.execute(
            "ask_user", {"questions": [{"field": "floor", "question": "층?", "reason": "확인"}]}
        )
        self.assertEqual(reply.error.code, "QUESTION_NOT_ALLOWED")
