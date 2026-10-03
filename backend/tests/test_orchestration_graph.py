"""실제 그래프 분기와 기존 호출·저장 계약의 연결을 검사합니다."""

import asyncio
import importlib.util
import json
import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.callbacks import AsyncCallbackHandler
from langgraph.graph import StateGraph
from orchestration_support import lq_supplement, run_flow

from app.agents.orchestration.tools import SupplementTool
from app.mocks import mock_agents, mock_generate, mock_resolve
from app.schemas import SupplementOperation


class GraphTests(unittest.IsolatedAsyncioTestCase):
    async def run_flow(self, **overrides):
        self.assertIsNotNone(
            importlib.util.find_spec("app.agents.orchestration.graph"),
            "그래프 실행 모듈이 필요합니다.",
        )
        options = dict(
            resolve=mock_resolve,
            agents=mock_agents(),
            generate=mock_generate,
            request_id="graph-test",
            radius_m=300,
        )
        options.update(overrides)
        return await run_flow("시험 주소", **options)

    async def test_graph_routes_supplement_back_to_decision_only(self):
        visited = []
        inputs = []
        calls = []

        class Trace(AsyncCallbackHandler):
            async def on_chain_start(self, serialized, inputs, **kwargs):
                name = kwargs.get("name")
                if name == (kwargs.get("metadata") or {}).get("langgraph_node"):
                    visited.append(name)

        compile_graph = StateGraph.compile

        def instrument(builder, *args, **kwargs):
            compiled = compile_graph(builder, *args, **kwargs)
            invoke = compiled.ainvoke

            async def tracked(value, config=None, **options):
                return await invoke(value, {**(config or {}), "callbacks": [Trace()]}, **options)

            compiled.ainvoke = tracked
            return compiled

        def generate(prompt, payload):
            data = json.loads(payload)
            inputs.append(data)
            if len(inputs) == 1:
                return {
                    "action": "supplement",
                    "requests": [
                        {
                            "agent_id": "commercial_area",
                            "operation": "test_detail",
                            "decision_question": "경쟁 근거를 유지할 수 있는가?",
                            "missing_information": "비교 자료",
                            "why_needed": "추천 판단에 필요",
                            "expected_impact": "경쟁 위험 설명 변경",
                        }
                    ],
                }
            return mock_generate(prompt, payload)

        async def execute(task, previous):
            calls.append((task.request_id, task.radius_m))
            previous.data["supplement_lq"] = lq_supplement(0)
            return previous

        tool = SupplementTool(
            operation=SupplementOperation(
                agent_id="commercial_area",
                operation="test_detail",
                description="시험용 상세",
            ),
            execute=execute,
            eligible=lambda task, previous: True,
        )
        with patch.object(StateGraph, "compile", instrument):
            result = await self.run_flow(generate=generate, supplements=[tool])
        self.assertEqual(
            visited,
            [
                "prepare_address",
                "run_analyses",
                "evaluate_decision",
                "execute_supplement",
                "evaluate_decision",
            ],
        )
        self.assertEqual(calls, [("graph-test", 300)])
        self.assertEqual(len(inputs), 2)
        self.assertNotIn("supplement_operations", inputs[1])
        self.assertEqual(result.source_analyses[2].data["supplement_lq"]["baseline_store_total"], 0)

    async def test_callback_failure_waits_for_started_analyses(self):
        finished = []
        agents = mock_agents()
        delayed = agents["commercial_area"]

        async def slow(task):
            await asyncio.sleep(0.01)
            result = await delayed(task)
            finished.append(task.request_id)
            return result

        async def save(result):
            if result.agent_id == "floating_population":
                raise OSError("저장 실패")

        agents["commercial_area"] = slow
        generate = AsyncMock(side_effect=AssertionError("판단 실행 금지"))
        with self.assertRaisesRegex(OSError, "저장 실패"):
            await self.run_flow(agents=agents, on_analysis_completed=save, generate=generate)
        self.assertEqual(finished, ["graph-test"])
        generate.assert_not_awaited()

    async def test_parallel_requests_do_not_share_graph_state(self):
        results = await asyncio.gather(
            self.run_flow(request_id="first", radius_m=150),
            self.run_flow(request_id="second", radius_m=700),
        )
        self.assertEqual([r.request_id for r in results], ["first", "second"])
        for result in results:
            self.assertEqual({a.request_id for a in result.source_analyses}, {result.request_id})
