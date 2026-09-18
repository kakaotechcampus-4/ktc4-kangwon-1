"""실제 SDK와 HTTP 대역으로 도구 호출 계약을 검사합니다."""

import json
import os
import unittest
from unittest.mock import patch

import httpx
import openai

from app.agents.orchestration import llm, tools


class ToolModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_request_and_response_errors(self):
        constructor = openai.AsyncOpenAI
        for status, finish in ((200, "tool_calls"), (200, "length"), (400, "stop")):
            with self.subTest(status=status, finish=finish):
                requests = []

                def respond(request, *, requests=requests, status=status, finish=finish):
                    requests.append(json.loads(request.content))
                    return httpx.Response(
                        status,
                        json={
                            "id": "test",
                            "object": "chat.completion",
                            "created": 0,
                            "model": "test",
                            "choices": [
                                {
                                    "index": 0,
                                    "finish_reason": finish,
                                    "message": {
                                        "role": "assistant",
                                        "tool_calls": [
                                            {
                                                "id": "call-1",
                                                "type": "function",
                                                "function": {
                                                    "name": "prepare_address",
                                                    "arguments": "{}",
                                                },
                                            }
                                        ],
                                    },
                                }
                            ],
                        },
                    )

                def make_client(**kwargs):
                    return constructor(
                        **kwargs,
                        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
                    )

                with (
                    patch.dict(
                        os.environ,
                        {
                            "ELICE_MODEL": "test",
                            "ELICE_API_KEY": "test",
                            "ELICE_BASE_URL": "https://test.invalid/v1",
                        },
                        clear=True,
                    ),
                    patch("app.llm.client.openai.AsyncOpenAI", side_effect=make_client),
                ):
                    if status == 200 and finish == "tool_calls":
                        result = await llm.generate_action(
                            [{"role": "user", "content": "시험"}], tools.TOOL_DEFINITIONS
                        )
                        self.assertEqual(result.tool_calls[0].function.name, "prepare_address")
                    else:
                        with self.assertRaises(RuntimeError):
                            await llm.generate_action([], tools.TOOL_DEFINITIONS)
                self.assertEqual(requests[0]["tool_choice"], "required")
                self.assertFalse(requests[0]["parallel_tool_calls"])
                self.assertNotIn("response_format", requests[0])

    async def test_missing_settings_do_not_call_api(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "ELICE_MODEL"):
                await llm.generate_action([], tools.TOOL_DEFINITIONS)


if __name__ == "__main__":
    unittest.main()
