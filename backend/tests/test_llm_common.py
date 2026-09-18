"""공통 모델 설정·전송을 실제 SDK와 가짜 HTTP 응답으로 검증합니다."""

import asyncio
import importlib
import io
import json
import os
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import httpx
import openai


class SettingsTests(unittest.TestCase):
    def settings_type(self):
        self.assertTrue((Path(__file__).parents[1] / "app/llm/config.py").exists())
        return importlib.import_module("app.llm.config").LLMSettings

    def test_agent_overrides_legacy_and_explicit_overrides_agent(self):
        settings_type = self.settings_type()
        with patch.dict(
            os.environ,
            {
                "ELICE_MODEL": "legacy",
                "ELICE_API_KEY": "secret",
                "ELICE_BASE_URL": "https://old.invalid/v1",
                "LLM_MAX_TOKENS": "123",
                "LLM_TIMEOUT_SECONDS": "45",
                "DECISION_LLM_MODEL": "decision",
                "DECISION_LLM_MAX_TOKENS": "456",
                "DECISION_LLM_REASONING_EFFORT": "low",
            },
            clear=True,
        ):
            settings = settings_type.from_env("DECISION", model="injected")
            self.assertEqual(
                (settings.model, settings.max_tokens, settings.timeout_seconds),
                ("injected", 456, 45),
            )
            self.assertEqual(settings.reasoning_effort, "low")
            self.assertEqual(settings_type.from_env("ORCHESTRATION").model, "legacy")
            self.assertNotIn("secret", repr(settings))
            with self.assertRaises(FrozenInstanceError):
                settings.model = "changed"

    def test_missing_credentials_are_deferred_but_bad_numbers_are_rejected(self):
        settings_type = self.settings_type()
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(settings_type.from_env("FLOATING_POPULATION").model)
            for field, value in (
                ("max_tokens", 0),
                ("max_tokens", 1.5),
                ("timeout_seconds", float("nan")),
                ("timeout_seconds", float("inf")),
                ("timeout_seconds", -1),
            ):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    settings_type(**{field: value})
        with patch.dict(os.environ, {"LLM_MAX_TOKENS": "bad"}, clear=True):
            self.assertEqual(settings_type.from_env("DECISION", max_tokens=7).max_tokens, 7)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.assertTrue((Path(__file__).parents[1] / "app/llm/client.py").exists())
        self.client = importlib.import_module("app.llm.client")
        self.settings_type = importlib.import_module("app.llm.config").LLMSettings
        self.settings = self.settings_type(
            model="test", api_key="secret", base_url="https://one.invalid/v1"
        )
        self.requests = []
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.enterContext(
            patch("socket.socket.connect", side_effect=AssertionError("외부 연결 금지"))
        )

    def transport(
        self, content='{"answer": 1}', finish="stop", refusal=None, status=200, choices=True
    ):
        def respond(request):
            self.requests.append((request.url.host, json.loads(request.content)))
            payload = {
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": finish,
                        "message": {"role": "assistant", "content": content, "refusal": refusal},
                    }
                ]
                if choices
                else [],
            }
            if status != 200:
                payload = {"error": {"message": "SECRET-UPSTREAM", "type": "invalid_request_error"}}
            if choices == "malformed":
                payload["choices"] = [None]
            elif choices == "object":
                payload["choices"] = {"SECRET-UPSTREAM": {}}
            elif choices == "number":
                payload["choices"] = 1
            return httpx.Response(status, json=payload)

        constructor = openai.AsyncOpenAI

        def make_client(**kwargs):
            return constructor(
                **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
            )

        return patch("app.llm.client.openai.AsyncOpenAI", side_effect=make_client)

    async def test_parallel_settings_keep_models_urls_and_optional_fields_separate(self):
        other = self.settings_type(
            model="other",
            api_key="other-secret",
            base_url="https://two.invalid/v1",
            max_tokens=None,
            reasoning_effort="low",
        )
        with self.transport():
            result = await asyncio.gather(
                self.client.complete_json("지침", "{}", self.settings),
                self.client.complete_json("지침", "{}", other),
            )
        self.assertEqual(result, [{"answer": 1}, {"answer": 1}])
        requests = {host: body for host, body in self.requests}
        self.assertEqual(requests["one.invalid"]["model"], "test")
        self.assertNotIn("reasoning_effort", requests["one.invalid"])
        self.assertEqual(requests["two.invalid"]["model"], "other")
        self.assertNotIn("max_completion_tokens", requests["two.invalid"])
        self.assertEqual(requests["two.invalid"]["reasoning_effort"], "low")
        self.assertIn("json", requests["one.invalid"]["messages"][0]["content"].lower())

    async def test_bad_responses_never_expose_provider_text(self):
        for case in (
            {"finish": "length"},
            {"refusal": "SECRET-UPSTREAM"},
            {"choices": False},
            {"choices": "malformed"},
            {"choices": "object"},
            {"choices": "number"},
            {"content": "SECRET-UPSTREAM"},
            {"content": "[]"},
            {"content": '{"x": NaN}'},
            {"status": 400},
        ):
            with self.subTest(case=case), self.transport(**case):
                with self.assertRaises(RuntimeError) as raised:
                    await self.client.complete_json("지침", "{}", self.settings)
                self.assertNotIn("SECRET-UPSTREAM", str(raised.exception))

    async def test_transient_http_retries_once_permanent_http_does_not(self):
        for status, count in ((500, 2), (401, 1)):
            self.requests.clear()
            with self.transport(status=status), self.assertRaises(RuntimeError):
                await self.client.complete_json("지침", "{}", self.settings)
            self.assertEqual(len(self.requests), count)

    async def test_missing_credentials_fail_before_transport(self):
        with self.transport(), self.assertRaises(ValueError):
            await self.client.complete_json("지침", "{}", self.settings_type())
        self.assertEqual(self.requests, [])


class EnvironmentTests(unittest.TestCase):
    def test_imports_do_not_load_environment_and_compatibility_aliases_use_backend_loader(self):
        self.assertTrue((Path(__file__).parents[1] / "app/config.py").exists())
        common = importlib.import_module("app.config")
        with patch("app.config.load_dotenv") as loader:
            for name in ("commercial_area", "floating_population", "business_lifecycle"):
                importlib.reload(importlib.import_module(f"app.agents.{name}.config"))
            for name in ("commercial_area", "floating_population"):
                module = importlib.import_module(f"app.agents.{name}.config")
                self.assertEqual(module.BACKEND_DIR, Path(__file__).resolve().parents[1])
                self.assertIs(module.load_dotenv_if_present, common.load_environment)
            loader.assert_not_called()
            common.load_environment()
            loader.assert_called_once_with(common.BACKEND_DIR / ".env", override=False)

    def test_client_constructor_does_not_load_dotenv(self):
        from app.agents.floating_population.client import SeoulOpenDataClient

        with (
            patch.dict(os.environ, {"FLOATING_POPULATION_API_KEY": "test"}, clear=True),
            patch("dotenv.load_dotenv") as loader,
            patch("app.config.load_dotenv") as common_loader,
        ):
            client = SeoulOpenDataClient()
            self.assertEqual(client.settings.api_key, "test")
        loader.assert_not_called()
        common_loader.assert_not_called()

    def test_server_loads_only_on_startup_once(self):
        async def start():
            module = importlib.import_module("app.main")
            with patch("app.config.load_dotenv") as loader:
                importlib.reload(module)
                loader.assert_not_called()
                from app.services.settings import ExecutionSettings

                with patch("app.main.initialize") as initialize:
                    app = module.create_app(
                        settings=ExecutionSettings(db_path="unused-test.sqlite3")
                    )
                    loader.assert_called_once()
                    initialize.assert_not_called()
                    async with app.router.lifespan_context(app):
                        loader.assert_called_once()
                        initialize.assert_called_once_with("unused-test.sqlite3")

        asyncio.run(start())

    def test_cli_entrypoints_load_environment_once(self):
        floating = importlib.import_module("app.agents.floating_population.__main__")
        with (
            patch("app.config.load_dotenv") as loader,
            patch("sys.argv", ["agent"]),
            patch("sys.stderr", new=io.StringIO()),
        ):
            self.assertEqual(floating.main(), 2)
            loader.assert_called_once()

        lifecycle = importlib.import_module("examples.run_business_lifecycle")
        result = {
            "industry_scores": [],
            "unavailable_industries": [],
            "summary": "테스트",
        }
        with (
            patch("app.config.load_dotenv") as loader,
            patch.object(lifecycle, "run_business_lifecycle_agent", return_value=result),
            patch("sys.argv", ["agent", "--area-code", "3120240", "--base-quarter", "20252"]),
            patch("sys.stdout", new=io.StringIO()),
        ):
            self.assertEqual(lifecycle.main(), 0)
            loader.assert_called_once()
