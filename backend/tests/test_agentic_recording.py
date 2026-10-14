"""모델 녹화·재생은 실제 도구 루프와 비밀값·동적 식별자 경계를 검증합니다."""

import asyncio
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from openai.types.chat import ChatCompletionMessage

from app.agents.agentic.recording import CallRecording, ReplayGenerate
from app.agents.agentic.registry import persist_report
from app.agents.agentic.runtime import DecisionLoop
from app.agents.agentic.scoring import WEIGHTS, result, summarize
from app.db.connection import initialize
from app.db.repository import create_request
from app.llm.budget import BudgetExceeded
from app.llm.client import LLMHTTPError, LLMResponseError
from app.schemas import Site
from app.storage.raw import capture_scope


def tool_message(name, arguments):
    return ChatCompletionMessage(
        role="assistant",
        tool_calls=[
            {
                "id": "call_recorded",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        ],
    )


class RecordingTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_fact_set_reordering_keeps_identity(self):
        first, second = "f_" + str(uuid.uuid4()), "f_" + str(uuid.uuid4())
        payload = {"fact_ids": [first, second], "by_metric": {"first": first, "second": second}}
        response = tool_message("get_facts", {"fact_ids": [first, second]})
        replay = ReplayGenerate(
            entries=[
                {
                    "role": "decision",
                    "messages": [{"role": "tool", "content": json.dumps(payload)}],
                    "value": response.model_dump(mode="json"),
                    "usage": None,
                    "model": "test",
                    "error": None,
                    "elapsed_ms": 120,
                }
            ]
        )
        payload["fact_ids"].reverse()
        receipt = {}
        value = await replay([{"role": "tool", "content": json.dumps(payload)}], [], None, receipt)
        self.assertEqual(
            json.loads(value.tool_calls[0].function.arguments)["fact_ids"], [first, second]
        )
        self.assertEqual(receipt["replay_elapsed_ms"], 120)

    async def test_cancelled_model_record_replays_as_timeout(self):
        replay = ReplayGenerate(
            entries=[
                {
                    "role": "decision",
                    "messages": [],
                    "value": None,
                    "usage": None,
                    "model": "test",
                    "error": {"type": "CancelledError", "code": "CancelledError"},
                }
            ]
        )
        with self.assertRaises(TimeoutError):
            await replay([], [], None, {})

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "calls.json"

    async def asyncTearDown(self):
        await asyncio.to_thread(self.temp.cleanup)

    async def read_entries(self):
        return json.loads(await asyncio.to_thread(self.path.read_text, encoding="utf-8"))

    async def test_full_raw_response_and_sent_messages_are_scrubbed_and_appended(self):
        recording = CallRecording(self.path)
        value = tool_message("get_scorecard", {"limit": 5})
        raw = {
            "choices": [{"message": {"content": "긴 원문" * 20000 + " fixture-private-key"}}],
            "api_key": "fixture-private-key",
        }
        receipt = {
            "raw_response": raw,
            "sent_messages": [{"role": "user", "content": "fixture-token fixture-secret"}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 20},
            "model": "fixture-model",
            "base_url": "https://private-provider.example",
            "api_key": "fixture-private-key",
        }
        with patch.dict(
            os.environ,
            {
                "RECORDING_API_KEY": "fixture-private-key",
                "RECORDING_TOKEN": "fixture-token",
                "RECORDING_SECRET": "fixture-secret",
            },
        ):
            await recording.record("decision", [], value, receipt, 17)
            await recording.record("advisor", [], {"status": "ok"}, {}, 3)
        entries = await self.read_entries()
        saved = json.dumps(entries, ensure_ascii=False)
        self.assertEqual(len(entries), 2)
        for secret in ("fixture-private-key", "fixture-token", "fixture-secret"):
            self.assertNotIn(secret, saved)
        self.assertNotIn("private-provider.example", saved)
        self.assertNotIn("api_key", saved)
        self.assertGreater(
            len(entries[0]["raw_response"]["choices"][0]["message"]["content"]), 50000
        )
        self.assertEqual(entries[0]["messages"][0]["content"], "[REDACTED] [REDACTED]")
        self.assertEqual(entries[0]["tool_calls"][0]["function"]["name"], "get_scorecard")
        self.assertEqual(entries[0]["elapsed_ms"], 17)
        self.assertEqual(entries[1]["raw_response"], {"status": "ok"})

    async def test_record_and_replay_run_same_tools_and_draft_with_new_scope_ids(self):
        recording = CallRecording(self.path)
        site = Site(input_address="시험", road_address="시험", latitude=37.5, longitude=127.0)
        rows = [
            summarize(code, {key: result(key) for key in WEIGHTS}, "해당 없음")
            for code in ["I201", "I202", "I203", "I204", "I210"]
        ]
        outputs, loops = [], []
        calls = 0

        async def generate(messages, definitions, settings, receipt):
            nonlocal calls
            calls += 1
            receipt.update(
                model="fixture-model", usage={"prompt_tokens": 30, "completion_tokens": 20}
            )
            return (
                tool_message("get_scorecard", {"limit": 5})
                if calls == 1
                else tool_message(
                    "submit_draft",
                    {
                        "phase": "draft",
                        "report": {
                            "summary_segments": [
                                {"type": "text", "text": "자료를 검토한 후보입니다."}
                            ]
                        },
                    },
                )
            )

        for index in range(2):
            database = Path(self.temp.name) / f"scope-{index}.sqlite3"
            request_id = str(uuid.uuid4())
            await asyncio.to_thread(initialize, database)
            await asyncio.to_thread(create_request, request_id, "시험", db_path=database)
            async with capture_scope(request_id, database) as scope:
                await asyncio.to_thread(persist_report, scope, {"rows": rows, "top5": rows}, {}, [])
                loop = await DecisionLoop.create(
                    scope,
                    site,
                    generate=generate if index == 0 else ReplayGenerate(self.path),
                    recorder=recording if index == 0 else None,
                )
                outputs.append(await loop.run())
                loops.append(loop)
        self.assertNotEqual(loops[0].scope.request_id, loops[1].scope.request_id)
        self.assertNotEqual(loops[0].base_id, loops[1].base_id)
        for loop, output in zip(loops, outputs, strict=True):
            self.assertEqual(loop.state["tool_sequence"], ["get_scorecard", "submit_draft"])
            self.assertEqual(output.status, "draft_available")
            self.assertEqual(output.result.summary_segments[0].text, "자료를 검토한 후보입니다.")
            self.assertEqual(
                [row.industry_code for row in output.result.top5], [r["code"] for r in rows]
            )
            self.assertEqual(loop.budget.totals(), (60, 40))
        self.assertEqual(len(await self.read_entries()), 2)

    async def test_uuid_refs_are_remapped_in_arguments_and_advisor_json_only(self):
        prefixes = [
            "request_",
            "s_",
            "f_",
            "tc_",
            "consult_",
            "sc_",
            "question_",
            "report_",
            "map_",
        ]
        recorded_ids = {prefix: prefix + str(uuid.uuid4()) for prefix in prefixes}
        current_ids = {prefix: prefix + str(uuid.uuid4()) for prefix in prefixes}
        sentence = "확인할 식별자는 " + recorded_ids["f_"] + "입니다."
        recorded_messages = [{"role": "user", "content": json.dumps(recorded_ids)}]
        current_messages = [{"role": "user", "content": json.dumps(current_ids)}]
        args = {"refs": list(recorded_ids.values()), "sentence": sentence}
        recording = CallRecording(self.path)
        await recording.record(
            "decision",
            recorded_messages,
            tool_message("submit_draft", args),
            {"model": "fixture-model", "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
            1,
        )
        await recording.record(
            "advisor",
            recorded_messages,
            {"consult_id": recorded_ids["consult_"], "content": json.dumps(args)},
            {},
            1,
        )
        replay = ReplayGenerate(entries=await self.read_entries())
        receipt = {}
        message = await replay(current_messages, [], None, receipt)
        actual = json.loads(message.tool_calls[0].function.arguments)
        self.assertEqual(actual["refs"], list(current_ids.values()))
        self.assertEqual(actual["sentence"], sentence)
        self.assertEqual(receipt["model"], "fixture-model")
        self.assertEqual(receipt["usage"], {"prompt_tokens": 10, "completion_tokens": 5})
        answer = await replay(current_messages, None, None, {})
        self.assertEqual(answer["consult_id"], current_ids["consult_"])
        self.assertEqual(json.loads(answer["content"])["refs"], list(current_ids.values()))
        self.assertEqual(json.loads(answer["content"])["sentence"], sentence)
        with self.assertRaisesRegex(ValueError, "녹화.*모두"):
            await replay(current_messages, [], None, {})

    async def test_recorded_failures_restore_error_code_usage_and_http_diagnostics(self):
        errors = [
            LLMResponseError("LLM_OUTPUT_LIMIT"),
            LLMHTTPError(429, {"error": {"code": "rate_limit_exceeded", "param": "model"}}),
            TimeoutError(),
            BudgetExceeded(),
        ]
        recording = CallRecording(self.path)
        for error in errors:
            await recording.record(
                "decision", [], None, {"usage": {"prompt_tokens": 7}, "model": "fixture"}, 8, error
            )
        replay = ReplayGenerate(self.path)
        for error in errors:
            receipt = {}
            with self.assertRaises(type(error)) as raised:
                await replay([], [], None, receipt)
            self.assertEqual(getattr(raised.exception, "code", None), getattr(error, "code", None))
            self.assertEqual(
                getattr(raised.exception, "diagnostics", None), getattr(error, "diagnostics", None)
            )
            self.assertEqual(receipt["usage"], {"prompt_tokens": 7})
            self.assertEqual(receipt["model"], "fixture")


if __name__ == "__main__":
    unittest.main()
