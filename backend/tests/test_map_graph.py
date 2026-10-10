"""지도 실행 제한과 보완·질문 분기를 검증합니다."""

import unittest
from unittest.mock import Mock

from orchestration_support import run_flow
from test_map_mapping import plan
from test_questions import question

from app.agents.map_analysis.agent import failed_observation
from app.llm.budget import BudgetStorageError
from app.mocks import mock_agents, mock_generate, mock_resolve


class MapGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_map_failure_contract(self):
        for error in (
            TimeoutError(),
            RuntimeError("외부 실패"),
            BudgetStorageError("저장 실패"),
            ValueError("계약 오류"),
            TypeError("계약 오류"),
        ):

            async def lookup(task, request, error=error):
                raise error

            generate = Mock(side_effect=[plan(), mock_generate("", "")])
            with self.subTest(error=type(error).__name__):
                if isinstance(error, (BudgetStorageError, ValueError, TypeError)):
                    with self.assertRaises(type(error)):
                        await self.run_flow(generate, lookup)
                    self.assertEqual(generate.call_count, 1)
                else:
                    result = await self.run_flow(generate, lookup)
                    code = "MAP_TIMEOUT" if isinstance(error, TimeoutError) else "MAP_FAILED"
                    self.assertEqual(result.map_observation.status, "error")
                    self.assertEqual(
                        {q.error for q in result.map_observation.data.queries.values()}, {code}
                    )

    async def test_both_orders_preserve_once_only_operations(self):
        from app.agents.orchestration.tools import SupplementTool
        from app.schemas import SupplementOperation, SupplementPlan

        supplement = SupplementPlan(
            action="supplement",
            requests=[
                {
                    "agent_id": "commercial_area",
                    "operation": "detail",
                    "decision_question": "경쟁 확인",
                    "missing_information": "상세",
                    "why_needed": "후보 비교",
                    "expected_impact": "순위 확인",
                }
            ],
        )
        for order in ([plan(), supplement], [supplement, plan()]):
            calls = []

            async def lookup(task, request, calls=calls):
                calls.append("map")
                return failed_observation(task, request, "TIMEOUT")

            async def refresh(task, previous, calls=calls):
                calls.append("supplement")
                return previous

            tool = SupplementTool(
                SupplementOperation(
                    agent_id="commercial_area", operation="detail", description="상세"
                ),
                refresh,
                lambda *_: True,
            )
            final = await self.run_flow(
                Mock(side_effect=[*order, mock_generate("", "")]), lookup, supplements=[tool]
            )
            self.assertEqual(sorted(calls), ["map", "supplement"])
            self.assertIsNotNone(final.map_observation)

    async def run_flow(self, generate, lookup, **kwargs):
        return await run_flow(
            "시험",
            resolve=mock_resolve,
            agents=mock_agents(),
            generate=generate,
            request_id="r",
            radius_m=300,
            map_lookup=lookup,
            **kwargs,
        )

    async def test_lookup_then_final_and_second_lookup_forbidden(self):
        calls = []

        async def lookup(task, request):
            calls.append(task)
            return failed_observation(task, request, "TIMEOUT")

        result = await self.run_flow(Mock(side_effect=[plan(), mock_generate("", "")]), lookup)
        self.assertEqual(result.map_observation.status, "error")
        self.assertEqual(calls[0].radius_m, 300)
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ValueError):
            await self.run_flow(Mock(return_value=plan()), lookup)
        self.assertEqual(len(calls), 2)

    async def test_lookup_then_question(self):
        saved = []

        async def lookup(task, request):
            return failed_observation(task, request, "TIMEOUT")

        async def save(*args):
            saved.append(args)

        result = await self.run_flow(
            Mock(side_effect=[plan(), {"action": "ask_user", "questions": [question()]}]),
            lookup,
            allow_questions=True,
            on_questions=save,
        )
        self.assertEqual(result.status, "waiting_for_input")
        self.assertEqual(len(saved), 1)

    async def test_wrong_observation_id_stops_decision(self):
        async def lookup(task, request):
            result = failed_observation(task, request, "TIMEOUT")
            return result.model_copy(update={"request_id": "another"})

        generate = Mock(side_effect=[plan(), mock_generate("", "")])
        with self.assertRaises(ValueError):
            await self.run_flow(generate, lookup)
        self.assertEqual(generate.call_count, 1)
