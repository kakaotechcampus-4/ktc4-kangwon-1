"""실제 SDK로 스트림 조립·사용량·불완전 종료를 검사합니다."""

import asyncio
import json
import unittest
from unittest.mock import patch

import httpx
import openai
from llm_stream_fixture import sse_response

from app.llm import client
from app.llm.budget import LLMBudget, llm_scope
from app.llm.config import LLMSettings


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    def transport(self, deltas, finish="stop"):
        chunks = [
            {
                "id": "test",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "test",
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
            for delta in deltas
        ]
        if finish:
            chunks.append(
                {**chunks[0], "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}
            )
        chunks.append(
            {
                **chunks[0],
                "choices": [],
                "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
            }
        )

        def respond(request):
            body = json.loads(request.content)
            self.assertTrue(body.get("stream"), "비스트리밍 요청은 프록시에서 거절됩니다.")
            self.assertEqual(body["stream_options"], {"include_usage": True})
            return sse_response(chunks)

        constructor = openai.AsyncOpenAI
        return patch(
            "app.llm.client.openai.AsyncOpenAI",
            side_effect=lambda **kwargs: constructor(
                **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
            ),
        )

    async def test_split_json_and_usage_are_preserved(self):
        budget = LLMBudget()
        with (
            self.transport([{"role": "assistant", "content": '{"ok":'}, {"content": "true}"}]),
            llm_scope(budget, "decision", final=True),
        ):
            result = await client.complete_json("", "{}", self.settings())
        self.assertEqual(result, {"ok": True})
        self.assertEqual(budget.calls[0]["input_tokens"], 12)
        self.assertEqual(budget.calls[0]["output_tokens"], 7)

    async def test_split_tool_arguments_are_preserved(self):
        with self.transport(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "finish", "arguments": '{"ok":'},
                        }
                    ],
                },
                {"tool_calls": [{"index": 0, "function": {"arguments": "true}"}}]},
            ],
            "tool_calls",
        ):
            result = await client.complete_tools([], [], self.settings())
        self.assertEqual(result.tool_calls[0].function.arguments, '{"ok":true}')
        self.assertEqual(result.tool_calls[0].id, "call-1")

    async def test_missing_finish_is_rejected_even_with_valid_json(self):
        with self.transport([{"role": "assistant", "content": '{"ok":true}'}], None):
            with self.assertRaises(client.LLMResponseError) as caught:
                await client.complete_json("", "{}", self.settings())
        self.assertEqual(caught.exception.code, "LLM_INCOMPLETE")

    async def test_interrupted_stream_closes_and_records_failed_call(self):
        for error, expected in (
            (httpx.ReadError("SECRET"), "LLM_CONNECTION_ERROR"),
            (httpx.ReadTimeout("SECRET"), "LLM_TIMEOUT"),
            (asyncio.CancelledError(), None),
        ):

            class BrokenStream(httpx.AsyncByteStream):
                closed = False

                def __init__(self, failure):
                    self.failure = failure

                async def __aiter__(self):
                    yield (
                        b'data: {"id":"x","created":0,"model":"test",'
                        b'"object":"chat.completion.chunk","choices":[{"index":0,'
                        b'"delta":{"role":"assistant","content":"{"},'
                        b'"finish_reason":null}]}\n\n'
                    )
                    raise self.failure

                async def aclose(self):
                    self.closed = True

            body = BrokenStream(error)
            sdk = openai.AsyncOpenAI(
                api_key="test",
                max_retries=0,
                http_client=httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda request, body=body: httpx.Response(
                            200, stream=body, headers={"content-type": "text/event-stream"}
                        )
                    )
                ),
            )
            budget = LLMBudget()
            with (
                patch("app.llm.client.openai.AsyncOpenAI", return_value=sdk),
                llm_scope(budget, "decision", final=True),
            ):
                with self.assertRaises(
                    client.LLMResponseError if expected else asyncio.CancelledError
                ) as caught:
                    await client.complete_json("", "{}", self.settings())
            if expected:
                self.assertEqual(caught.exception.code, expected)
                self.assertNotIn("SECRET", str(caught.exception))
            self.assertTrue(body.closed)
            self.assertEqual(budget.used, 1)
            self.assertEqual(budget.calls[0]["status"], "error")

    def settings(self):
        return LLMSettings(model="test", api_key="test", base_url="https://test.invalid/v1")
