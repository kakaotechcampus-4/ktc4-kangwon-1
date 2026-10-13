"""모델 연결의 실행 범위 재사용·분리·정리를 가짜 HTTP로 검사합니다."""

import asyncio
import socket
import unittest
from dataclasses import replace
from unittest.mock import patch

import httpx
import openai
from llm_stream_fixture import stream_response

from app.llm.client import complete_json
from app.llm.config import LLMSettings
from app.llm.session import acquire_client, client_session_scope


class LLMSessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.socket_connect = socket.socket.connect
        self.settings = LLMSettings(
            model="test", api_key="test", base_url="https://test.invalid/v1"
        )
        self.created, self.closed, self.requests = [], [], []
        original = openai.AsyncOpenAI

        def respond(request):
            self.requests.append(request)
            return stream_response(
                json={
                    "id": "test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "test",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "{}"},
                        }
                    ],
                }
            )

        def factory(**options):
            client = original(
                **options, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
            )
            self.created.append(options)
            original_close = client.close

            async def close():
                self.closed.append(client)
                await original_close()

            client.close = close
            return client

        self.enterContext(patch("openai.AsyncOpenAI", side_effect=factory))
        self.enterContext(
            patch("socket.socket.connect", side_effect=AssertionError("network forbidden"))
        )

    async def test_same_settings_reuse_connection_until_execution_end(self):
        async with client_session_scope():
            await complete_json("json", "{}", self.settings)
            await complete_json("json", "{}", self.settings)
            self.assertEqual(len(self.created), 1)
            self.assertEqual(self.closed, [])
        self.assertEqual(len(self.closed), 1)
        self.assertEqual(len(self.requests), 2)

    async def test_different_credentials_and_urls_are_separate(self):
        async with client_session_scope():
            for settings in (
                self.settings,
                replace(self.settings, api_key="other"),
                replace(self.settings, base_url="https://other.invalid/v1"),
            ):
                await complete_json("json", "{}", settings)
        self.assertEqual(len(self.created), 3)
        self.assertEqual(len(self.closed), 3)

    async def test_exception_and_cancellation_close_clients(self):
        for error in (ValueError("test"), asyncio.CancelledError()):
            with self.assertRaises(type(error)):
                async with client_session_scope():
                    await complete_json("json", "{}", self.settings)
                    raise error
        self.assertEqual(len(self.closed), 2)

    async def test_clients_are_not_shared_across_execution_scopes_or_direct_calls(self):
        for _ in range(2):
            async with client_session_scope():
                await complete_json("json", "{}", self.settings)
        await complete_json("json", "{}", self.settings)
        self.assertEqual(len(self.created), 3)
        self.assertEqual(len(self.closed), 3)

    async def test_inherited_scope_rejects_another_event_loop(self):
        async def foreign_loop():
            async with acquire_client(self.settings, max_retries=1):
                self.fail("foreign loop used the session")

        async with client_session_scope():
            await complete_json("json", "{}", self.settings)
            # Windows 루프 생성의 내부 socketpair만 허용한 뒤 외부 연결 금지를 복원합니다.
            with patch("socket.socket.connect", self.socket_connect):
                loop = asyncio.new_event_loop()
            with self.assertRaises(RuntimeError):
                try:
                    await asyncio.to_thread(lambda: loop.run_until_complete(foreign_loop()))
                finally:
                    loop.close()
        self.assertEqual(len(self.created), 1)
