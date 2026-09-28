"""질문 분기와 재개가 기존 분석을 반복하지 않는지 검사합니다."""

import unittest
from unittest.mock import AsyncMock, Mock

from test_questions import question

from app.agents.orchestration import graph
from app.agents.orchestration.workflow import run_react
from app.mocks import mock_action, mock_agents, mock_generate, mock_resolve
from app.schemas import DecisionRequest, DecisionResult, LandlordAnswer, WaitingForInput


class QuestionGraphTests(unittest.IsolatedAsyncioTestCase):
    async def run_flow(self, **changes):
        args = dict(
            resolve=mock_resolve,
            agents=mock_agents(),
            generate_action=mock_action,
            generate=Mock(return_value=dict(action="ask_user", questions=[question()])),
            request_id="r",
        )
        args.update(changes)
        return await run_react("시험 주소", **args)

    async def test_wait_then_resume_only_decision(self):
        saved, sources = [], []

        async def on_questions(task, waiting, done, feedback):
            saved.append((task, waiting, done, feedback))

        async def on_analysis(result):
            sources.append(result)

        resolve = AsyncMock(side_effect=mock_resolve)
        result = await self.run_flow(
            resolve=resolve,
            allow_questions=True,
            on_questions=on_questions,
            on_analysis_completed=on_analysis,
        )
        self.assertIsInstance(result, WaitingForInput)
        self.assertEqual(len(saved), 1)
        request = DecisionRequest(
            request_id="r", address=saved[0][0].site.input_address, analyses=sources
        )
        final = await graph.resume_graph(
            request,
            site=saved[0][0].site,
            answers=[LandlordAnswer(field="floor", status="unknown")],
            feedback=[],
            supplement_context=[],
            generate=mock_generate,
        )
        self.assertIsInstance(final, DecisionResult)
        self.assertEqual(resolve.await_count, 1)
        self.assertEqual(len(sources), 3)

    async def test_save_failure_propagates_and_disabled_flow_cannot_ask(self):
        with self.assertRaises(OSError):
            await self.run_flow(
                allow_questions=True, on_questions=AsyncMock(side_effect=OSError("저장 실패"))
            )
        with self.assertRaises(ValueError):
            await self.run_flow()
        with self.assertRaises(ValueError):
            await self.run_flow(allow_questions=True)
