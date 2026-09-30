"""실제 판단 검증기를 통과하는 질문 분기를 검사합니다."""

import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from test_questions import question

from app.agents.decision.agent import evaluate
from app.agents.decision.llm import generate_decision
from app.mocks import mock_agents, mock_generate, mock_site
from app.schemas import AnalysisTask, DecisionRequest, LandlordAnswer, QuestionPlan


class QuestionDecisionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.task = AnalysisTask(request_id="r", site=mock_site())
        self.request = DecisionRequest(
            request_id="r",
            address=self.task.site.input_address,
            analyses=[await f(self.task) for f in mock_agents().values()],
        )
        self.plan = dict(action="ask_user", questions=[question()])

    async def test_allowed_question_and_known_answer_exclusion(self):
        result = await evaluate(
            self.request, question_fields=["floor"], generate=Mock(return_value=self.plan)
        )
        self.assertIsInstance(result, QuestionPlan)
        for options in (
            {},
            {"question_fields": ["exclusive_area"]},
            {
                "question_fields": ["floor"],
                "user_answers": [LandlordAnswer(field="floor", status="answered", value="2층")],
            },
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                await evaluate(self.request, generate=Mock(return_value=self.plan), **options)

    async def test_final_after_skipping_preserves_sources(self):
        generate = Mock(side_effect=mock_generate)
        result = await evaluate(
            self.request,
            user_answers=[LandlordAnswer(field="floor", status="skipped")],
            site=self.task.site,
            generate=generate,
        )
        self.assertEqual(result.source_analyses, self.request.analyses)
        payload = json.loads(generate.call_args.args[1])
        self.assertEqual(payload["user_answers"][0]["status"], "skipped")
        self.assertEqual(payload["site"]["detail_address"], "155호")
        self.assertTrue(any("floor" in item for item in result.limitations))

    async def test_correction_cannot_ask_question(self):
        broken = mock_generate("", "")
        broken["recommendations"][0]["evidence"][0]["path"] = "/missing"
        generate = Mock(side_effect=[broken, self.plan])
        with self.assertRaises(ValueError):
            await evaluate(self.request, question_fields=["floor"], generate=generate)
        self.assertEqual(generate.call_count, 2)

    async def test_llm_parser_returns_question(self):
        with patch(
            "app.agents.decision.llm.client.complete_json", AsyncMock(return_value=self.plan)
        ):
            result = await generate_decision("json", "{}", settings=object())
        self.assertIsInstance(result, QuestionPlan)
