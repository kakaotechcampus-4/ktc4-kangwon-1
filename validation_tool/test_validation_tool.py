"""외부 호출 없이 실제 서비스의 실행·기록·저장을 확인합니다."""

import asyncio
import importlib
import importlib.util
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from app.db import repository
from app.mocks import mock_action, mock_agents, mock_generate, mock_resolve
from app.services.settings import ExecutionSettings

ADDRESS = "서울특별시 송파구 가락동 167, 시험용 3층"
SECRET = "PRIVATE-KEY-DO-NOT-LOG"


class ValidationToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.console = StringIO()
        self.enterContext(redirect_stdout(self.console))
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("외부 호출 금지")))

    def runner(self):
        self.assertIsNotNone(importlib.util.find_spec("validation_tool.run"), "검증 도구가 없습니다.")
        return importlib.import_module("validation_tool.run").run

    async def execute(self, **overrides):
        options = dict(runs_dir=self.root, settings=ExecutionSettings(), resolve=mock_resolve,
                       agents=mock_agents(), generate_action=mock_action, generate=mock_generate)
        options.update(overrides)
        return await self.runner()(ADDRESS, **options)

    def records(self, folder):
        return [json.loads(line) for line in (folder / "trace.jsonl").read_text("utf-8").splitlines()]

    async def test_parallel_steps_and_separate_database(self):
        reached = set()
        ready = asyncio.Event()

        def parallel(agent_id, original):
            async def call(task):
                reached.add(agent_id)
                if len(reached) == 3:
                    ready.set()
                await asyncio.wait_for(ready.wait(), 1)
                return await original(task)
            return call

        agents = {key: parallel(key, call) for key, call in mock_agents().items()}
        folder = await self.execute(agents=agents)
        result = json.loads((folder / "result.json").read_text("utf-8"))
        self.assertEqual(result["address"], ADDRESS)
        self.assertEqual(result["request_id"], folder.name)
        db = folder / "analysis.sqlite3"
        self.assertEqual(repository.get_request(folder.name, db_path=db)["status"], "completed")
        self.assertEqual(len(repository.list_agent_results(folder.name, db_path=db)), 3)
        self.assertEqual(len(repository.list_decision_results(folder.name, db_path=db)), 1)
        events = self.records(folder)
        self.assertEqual([e["tool"] for e in events if "tool" in e],
                         ["prepare_address", "run_analyses", "make_decision"])
        self.assertTrue(all(e["request_id"] == folder.name for e in events))
        self.assertEqual((events[-1]["stage"], events[-1]["event"]), ("run", "completed"))
        self.assertTrue(any(e["stage"] == "address" and "site" in e for e in events))
        self.assertTrue(any(e["stage"] == "storage" and e["decision_count"] == 1 for e in events))

    async def test_agent_failure_keeps_partial_result_without_raw_error(self):
        async def fail(task):
            raise RuntimeError(f"https://private.example/{SECRET}")

        agents = mock_agents()
        agents["business_lifecycle"] = fail
        folder = await self.execute(agents=agents)
        result = json.loads((folder / "result.json").read_text("utf-8"))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["source_analyses"]), 3)
        trace = (folder / "trace.jsonl").read_text("utf-8")
        self.assertNotIn(SECRET, trace + self.console.getvalue())
        self.assertNotIn("private.example", trace)
        self.assertTrue(any(e["stage"] == "business_lifecycle" and e["event"] == "failed"
                            for e in self.records(folder)))

    async def test_address_failure_is_stored_without_analysis_or_raw_error(self):
        async def fail(address):
            raise RuntimeError(SECRET)

        with self.assertRaises(RuntimeError):
            await self.execute(resolve=fail)
        folder = next(self.root.iterdir())
        row = repository.get_request(folder.name, db_path=folder / "analysis.sqlite3")
        self.assertEqual(row["status"], "failed")
        self.assertFalse((folder / "result.json").exists())
        events = self.records(folder)
        self.assertFalse(any(e["stage"] == "floating_population" for e in events))
        self.assertEqual(events[-1]["event"], "failed")
        self.assertNotIn(SECRET, (folder / "trace.jsonl").read_text("utf-8") + self.console.getvalue())

    async def test_decision_contract_failure_preserves_analyses(self):
        def invalid(prompt, payload):
            result = mock_generate(prompt, payload)
            result["recommendations"][0]["category"]["middle"] = "미등록 시험 업종"
            return result

        with self.assertRaises(ValueError):
            await self.execute(generate=invalid)
        folder = next(self.root.iterdir())
        db = folder / "analysis.sqlite3"
        self.assertEqual(repository.get_request(folder.name, db_path=db)["status"], "failed")
        self.assertEqual(len(repository.list_agent_results(folder.name, db_path=db)), 3)
        self.assertEqual(repository.list_decision_results(folder.name, db_path=db), [])
        self.assertFalse((folder / "result.json").exists())

    async def test_cancel_records_terminal_event_after_service_cleanup(self):
        started = asyncio.Event()

        async def waiting(address):
            started.set()
            await asyncio.Event().wait()

        # 진입점이 없을 때 대기 시간 초과가 아닌 명확한 실패를 남깁니다.
        self.runner()
        task = asyncio.create_task(self.execute(resolve=waiting))
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        folder = next(self.root.iterdir())
        self.assertEqual(self.records(folder)[-1]["event"], "cancelled")
        self.assertEqual(repository.get_request(folder.name, db_path=folder / "analysis.sqlite3")["status"], "failed")

    async def test_empty_address_creates_nothing(self):
        with self.assertRaises(ValueError):
            await self.runner()("  ", runs_dir=self.root, settings=ExecutionSettings())
        self.assertEqual(list(self.root.iterdir()), [])
