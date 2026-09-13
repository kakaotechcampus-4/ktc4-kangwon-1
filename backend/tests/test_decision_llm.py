"""엘리스 OpenAI 호환 호출을 검사합니다."""

import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agents.decision.llm import generate_decision

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "decision"
BASE_ENV = {
    key: value for key, value in os.environ.items() if not key.startswith(("ELICE_", "LLM_"))
}


@unittest.skipUnless(
    importlib.util.find_spec("openai"), "OpenAI 호환 라이브러리가 설치되지 않았습니다."
)
class ModelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.content = json.loads((EXAMPLES / "response.json").read_text(encoding="utf-8"))

    async def test_missing_elice_configuration_is_clear(self):
        settings = [
            ({}, "ELICE_MODEL"),
            ({"ELICE_MODEL": "test-model"}, "ELICE_API_KEY"),
            ({"ELICE_MODEL": "test-model", "ELICE_API_KEY": "test"}, "ELICE_BASE_URL"),
            (
                {
                    "ELICE_MODEL": "test-model",
                    "ELICE_API_KEY": "test",
                    "ELICE_BASE_URL": "https://elice.example/v1",
                    "LLM_TIMEOUT_SECONDS": "nan",
                },
                "양수",
            ),
        ]
        for environment, message in settings:
            with (
                self.subTest(environment=environment),
                patch.dict(os.environ, {**BASE_ENV, **environment}, clear=True),
            ):
                with self.assertRaisesRegex(ValueError, message):
                    await generate_decision("시험용 지침", "{}")

    async def test_elice_compatible_request_returns_valid_content(self):
        import httpx
        import openai

        requests = []

        def respond(request):
            requests.append(json.loads(request.content))
            self.assertEqual(request.url.path, "/v1/chat/completions")
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "test-model",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(self.content),
                                "refusal": None,
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                },
            )

        constructor = openai.AsyncOpenAI

        def make_client(**kwargs):
            return constructor(
                **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
            )

        environment = {
            "ELICE_MODEL": "test-model",
            "ELICE_API_KEY": "test",
            "ELICE_BASE_URL": "https://elice.example/v1",
        }
        with (
            patch.dict(os.environ, {**BASE_ENV, **environment}, clear=True),
            patch("openai.AsyncOpenAI", side_effect=make_client),
        ):
            result = await generate_decision("시험용 지침", "{}")
        self.assertEqual(result.recommendations[0].score, 72)
        self.assertEqual(requests[0]["messages"][0]["content"], "시험용 지침")
        self.assertEqual(requests[0]["messages"][1]["content"], "{}")
        self.assertEqual(requests[0]["response_format"]["type"], "json_object")
        self.assertEqual(requests[0]["max_completion_tokens"], 8192)
        self.assertNotIn("max_tokens", requests[0])

    async def test_elice_response_without_json_is_rejected(self):
        import httpx
        import openai

        constructor = openai.AsyncOpenAI

        def make_client(**kwargs):
            response = {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "분석 결과입니다.",
                            "refusal": None,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            }
            return constructor(
                **kwargs,
                http_client=httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda request: httpx.Response(200, json=response)
                    )
                ),
            )

        environment = {
            "ELICE_MODEL": "test-model",
            "ELICE_API_KEY": "test",
            "ELICE_BASE_URL": "https://elice.example/v1",
        }
        with (
            patch.dict(os.environ, {**BASE_ENV, **environment}, clear=True),
            patch("openai.AsyncOpenAI", side_effect=make_client),
        ):
            with self.assertRaisesRegex(RuntimeError, "응답 형식"):
                await generate_decision("시험용 지침", "{}")

    async def test_elice_response_error_shows_invalid_field(self):
        import httpx
        import openai

        constructor = openai.AsyncOpenAI

        def make_client(**kwargs):
            response = {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": '{"status":"ok"}',
                            "refusal": None,
                        },
                        "finish_reason": "stop",
                    }
                ],
            }
            return constructor(
                **kwargs,
                http_client=httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda request: httpx.Response(200, json=response)
                    )
                ),
            )

        environment = {
            "ELICE_MODEL": "test-model",
            "ELICE_API_KEY": "test",
            "ELICE_BASE_URL": "https://elice.example/v1",
        }
        with (
            patch.dict(os.environ, {**BASE_ENV, **environment}, clear=True),
            patch("openai.AsyncOpenAI", side_effect=make_client),
        ):
            with self.assertRaisesRegex(RuntimeError, "summary"):
                await generate_decision("시험용 지침", "{}")

    async def test_elice_request_error_shows_status_and_message(self):
        import httpx
        import openai

        constructor = openai.AsyncOpenAI

        def make_client(**kwargs):
            response = {
                "error": {
                    "message": "지원하지 않는 요청 필드입니다.",
                    "type": "invalid_request_error",
                }
            }
            return constructor(
                **kwargs,
                http_client=httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda request: httpx.Response(400, json=response)
                    )
                ),
            )

        environment = {
            "ELICE_MODEL": "test-model",
            "ELICE_API_KEY": "test",
            "ELICE_BASE_URL": "https://elice.example/v1",
        }
        with (
            patch.dict(os.environ, {**BASE_ENV, **environment}, clear=True),
            patch("openai.AsyncOpenAI", side_effect=make_client),
        ):
            with self.assertRaisesRegex(RuntimeError, "HTTP 400.*지원하지 않는 요청 필드"):
                await generate_decision("시험용 지침", "{}")


if __name__ == "__main__":
    unittest.main()
