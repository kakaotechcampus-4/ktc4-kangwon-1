"""모델 원문 없이 실패 원인을 구분하는지 검사합니다."""

import unittest
from unittest.mock import patch

import httpx
import openai
from openai.types.chat import ChatCompletionMessage

from app.agents.decision.llm import generate_decision
from app.llm.client import LLMResponseError, complete_json
from app.llm.config import LLMSettings


class DiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_transport_errors_are_distinct(self):
        from unittest.mock import AsyncMock, MagicMock

        request = httpx.Request("POST", "https://test.invalid/SECRET")
        for error, code in (
            (openai.APITimeoutError(request=request), "LLM_TIMEOUT"),
            (openai.APIConnectionError(request=request, message="SECRET"), "LLM_CONNECTION_ERROR"),
        ):
            fake = MagicMock()
            fake.chat.completions.create = AsyncMock(side_effect=error)
            context = AsyncMock()
            context.__aenter__.return_value = fake
            with patch("openai.AsyncOpenAI", return_value=context):
                with self.assertRaises(LLMResponseError) as caught:
                    await complete_json(
                        "",
                        "{}",
                        LLMSettings(api_key="test", model="test", base_url="https://test.invalid"),
                    )
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn("SECRET", str(caught.exception))

    async def test_finish_reason_is_safe_and_distinct(self):
        constructor = openai.AsyncOpenAI
        for finish, refusal, expected in (
            ("length", None, "LLM_OUTPUT_LIMIT"),
            ("stop", "SECRET", "LLM_REFUSED"),
            ("content_filter", None, "LLM_REFUSED"),
            ("SECRET", None, "LLM_INCOMPLETE"),
        ):
            response = {
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": finish,
                        "message": {"role": "assistant", "content": "SECRET", "refusal": refusal},
                    }
                ],
            }

            def make_client(response=response, **kwargs):
                return constructor(
                    **kwargs,
                    http_client=httpx.AsyncClient(
                        transport=httpx.MockTransport(
                            lambda request: httpx.Response(200, json=response)
                        )
                    ),
                )

            with (
                self.subTest(finish=finish, refusal=refusal),
                patch("openai.AsyncOpenAI", side_effect=make_client),
            ):
                with self.assertRaises(LLMResponseError) as caught:
                    await complete_json(
                        "",
                        "{}",
                        LLMSettings(api_key="test", model="test", base_url="https://test.invalid"),
                    )
                self.assertEqual(caught.exception.code, expected)
                self.assertNotIn(
                    "SECRET", str(caught.exception) + str(caught.exception.diagnostics)
                )

    async def test_invalid_json_is_distinct(self):
        with patch(
            "app.llm.client._complete",
            return_value=ChatCompletionMessage(role="assistant", content="SECRET"),
        ):
            with self.assertRaises(LLMResponseError) as caught:
                await complete_json("", "{}", LLMSettings())
        self.assertEqual(caught.exception.code, "LLM_INVALID_JSON")
        self.assertNotIn("SECRET", str(caught.exception))

    async def test_schema_fields_are_safe(self):
        with patch(
            "app.agents.decision.llm.client.complete_json",
            return_value={"status": "ok", "SECRET": "SECRET"},
        ):
            with self.assertRaises(LLMResponseError) as caught:
                await generate_decision("", "{}", settings=LLMSettings())
        self.assertEqual(caught.exception.code, "LLM_SCHEMA_INVALID")
        self.assertIn("summary", str(caught.exception.diagnostics))
        self.assertNotIn("SECRET", str(caught.exception) + str(caught.exception.diagnostics))
