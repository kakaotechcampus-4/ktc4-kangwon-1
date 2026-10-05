"""노드를 그래프 실행 없이 대역 의존성으로 직접 검증합니다."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.agents.orchestration.graph import RunHooks
from app.agents.orchestration.nodes.analysis import prepare_address, run_analyses
from app.agents.orchestration.nodes.tools import ask_user
from app.mocks import mock_agents, mock_site
from app.schemas import AnalysisTask


class NodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_address_uses_dependency_and_reports_saved_task(self):
        site = mock_site()
        saved = AsyncMock()
        deps = SimpleNamespace(
            address=site.input_address,
            resolve=AsyncMock(return_value=site),
            radius_m=300,
            request_id="node-test",
            step=AsyncMock(),
            hooks=RunHooks(on_task_prepared=saved),
        )
        result = await prepare_address({}, deps=deps)
        self.assertEqual(result["task"].site, site)
        saved.assert_awaited_once_with(result["task"])
        self.assertEqual(deps.step.await_args_list[-1].args, ("address", "completed"))

    async def test_run_analyses_collects_three_results_and_calls_hooks(self):
        completed = AsyncMock()
        deps = SimpleNamespace(
            agents=mock_agents(),
            agent_timeout=1,
            step=AsyncMock(),
            hooks=RunHooks(on_analysis_completed=completed),
        )
        task = AnalysisTask(request_id="node-test", site=mock_site(), radius_m=300)
        result = await run_analyses({"task": task}, deps=deps)
        self.assertEqual(len(result["analyses"]), 3)
        self.assertEqual(completed.await_count, 3)
        self.assertEqual({item.request_id for item in result["analyses"]}, {"node-test"})

    async def test_question_node_rejects_without_storage_hook(self):
        deps = SimpleNamespace(allow_questions=True, hooks=RunHooks())
        with self.assertRaisesRegex(ValueError, "질문을 저장할 수 없는 실행입니다."):
            await ask_user({"outcome": None}, deps=deps)
