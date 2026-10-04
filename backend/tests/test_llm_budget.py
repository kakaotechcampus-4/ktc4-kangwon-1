"""병렬 실행·실패·재개가 호출 상한을 우회하지 않는지 확인합니다."""

import asyncio
import importlib.util
import unittest
from unittest.mock import patch

import httpx
from openai import AsyncOpenAI

from app.llm import client
from app.llm.config import LLMSettings


class BudgetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("app.llm.budget"))
        from app.llm.budget import BudgetExceeded, LLMBudget, llm_scope

        self.budget_class, self.exceeded, self.scope = LLMBudget, BudgetExceeded, llm_scope

    async def test_parallel_specialists_leave_two_final_calls(self):
        budget = self.budget_class(limit=12)
        results = await asyncio.gather(
            *(budget.reserve("expert", final=False) for _ in range(15)),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(r, int) for r in results), 10)
        self.assertEqual(budget.used, 10)
        await budget.reserve("decision", final=True)
        await budget.reserve("decision", final=True)
        with self.assertRaises(self.exceeded):
            await budget.reserve("decision", final=True)
        restored = self.budget_class(limit=12, used=budget.used)
        with self.assertRaises(self.exceeded):
            await restored.reserve("decision", final=True)

    async def test_http_failure_consumes_one_call_without_hidden_retry(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(500, json={"error": {"code": "invalid_request_error"}})

        sdk = AsyncOpenAI(
            api_key="test",
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        )
        budget = self.budget_class()
        with (
            patch.object(client.openai, "AsyncOpenAI", return_value=sdk),
            self.scope(budget, "decision", final=True),
        ):
            with self.assertRaises(client.LLMHTTPError):
                await client.complete_json(
                    "판정",
                    "{}",
                    LLMSettings(
                        api_key="test", model="test", base_url="https://example.invalid/v1"
                    ),
                )
        self.assertEqual(len(requests), 1)
        self.assertEqual(budget.used, 1)
        self.assertEqual(budget.calls[0]["status"], "error")
        self.assertIsNone(budget.calls[0]["input_tokens"])

    async def test_failed_budget_storage_prevents_model_call(self):
        async def fail(_state):
            raise OSError("저장 실패")

        budget = self.budget_class(on_change=fail)
        from app.llm.budget import BudgetStorageError

        with self.assertRaises(BudgetStorageError):
            await budget.reserve("decision", final=True)
