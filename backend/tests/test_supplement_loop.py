"""실제 분석기를 수정하지 않고 보완 루프와 저장 계약을 검증합니다."""

import asyncio
import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from app.agents.decision.llm import generate_decision
from app.agents.orchestration.tools import SupplementTool
from app.db import repository
from app.db.connection import connect, initialize
from app.llm.config import LLMSettings
from app.mocks import mock_action, mock_agents, mock_generate, mock_resolve
from app.schemas import SupplementOperation, SupplementPlan
from app.services.analysis import execute_analysis
from app.services.settings import ExecutionSettings


class SupplementTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "analysis.sqlite3"
        self.enterContext(
            patch("socket.socket.connect", side_effect=AssertionError("외부 호출 금지"))
        )
        self.calls = []
        self.inputs = []

    async def supplement(self, task, previous):
        self.calls.append((task.request_id, task.radius_m))
        previous.data["office_worker_share"] = 0.5
        return previous

    def tool(self, execute=None, eligible=None):
        return SupplementTool(
            operation=SupplementOperation(
                agent_id="floating_population",
                operation="refresh_failed_block",
                description="실패한 블록만 다시 조회하는 시험용 작업",
            ),
            execute=execute or self.supplement,
            eligible=eligible or (lambda task, previous: True),
        )

    def generate(self, prompt, payload):
        self.inputs.append(json.loads(payload))
        if len(self.inputs) == 1:
            return {
                "action": "supplement",
                "requests": [
                    {
                        "agent_id": "floating_population",
                        "operation": "refresh_failed_block",
                        "decision_question": "직장인 수요를 추천 근거로 사용할 수 있는가?",
                        "missing_information": "직장인 비중의 추가 확인",
                        "why_needed": "현재 추천이 직장인 수요에 의존합니다.",
                        "expected_impact": "수요 근거를 유지할지 보류할지 결정합니다.",
                    }
                ],
            }
        return mock_generate(prompt, payload)

    async def run_service(self, **overrides):
        options = dict(
            db_path=self.path,
            request_id="test",
            radius_m=300,
            resolve=mock_resolve,
            agents=mock_agents(),
            generate_action=mock_action,
            generate=self.generate,
            settings=ExecutionSettings(),
            supplements=[self.tool()],
        )
        options.update(overrides)
        return await execute_analysis("시험 주소", **options)

    async def test_target_only_and_saved_source_attempts(self):
        result = await self.run_service()
        self.assertEqual(self.calls, [("test", 300)])
        self.assertEqual(len(self.inputs), 2)
        context = self.inputs[1]["supplement_context"][0]
        self.assertIn("직장인", context["request"]["decision_question"])
        self.assertTrue(context["adopted"])
        self.assertNotIn("analysis", context)
        self.assertEqual(result.source_analyses[0].data["office_worker_share"], 0.5)
        rows = repository.list_agent_results("test", db_path=self.path)
        self.assertEqual(len(rows), 4)
        original = next(
            json.loads(r["analysis_json"])
            for r in rows
            if r["agent_id"] == "floating_population" and r["attempt"] == 1
        )
        self.assertEqual(original["data"]["office_worker_share"], 0.41)
        decision = repository.list_decision_results("test", db_path=self.path)[0]
        self.assertEqual(
            json.loads(decision["source_attempts_json"]),
            {
                "floating_population": 2,
                "commercial_area": 1,
                "business_lifecycle": 1,
            },
        )
        events = repository.list_supplement_events("test", db_path=self.path)
        self.assertEqual([e["status"] for e in events], ["requested", "succeeded"])

    async def test_failure_preserves_original_and_records_limitation(self):
        async def fail(task, previous):
            previous.data.clear()
            raise RuntimeError("비밀키는 기록하지 않음")

        result = await self.run_service(supplements=[self.tool(execute=fail)])
        self.assertEqual(result.source_analyses[0].data["office_worker_share"], 0.41)
        self.assertEqual(result.status, "partial")
        self.assertTrue(any("보완" in text for text in result.limitations))
        rows = repository.list_supplement_events("test", db_path=self.path)
        self.assertEqual(rows[-1]["status"], "failed")
        self.assertNotIn("비밀키", str(rows))
        self.assertEqual(self.inputs[1]["supplement_context"][0]["status"], "failed")

    async def test_partial_can_finish_without_supplement(self):
        agents = mock_agents()
        original = agents["floating_population"]

        async def partial_source(task):
            result = await original(task)
            result.status = "partial"
            result.warnings = ["판단에 사용하지 않는 자료 누락"]
            return result

        agents["floating_population"] = partial_source
        result = await self.run_service(agents=agents, generate=mock_generate)
        self.assertEqual(result.status, "partial")
        self.assertEqual(self.calls, [])
        self.assertEqual(repository.list_supplement_events("test", db_path=self.path), [])

    def test_request_requires_decision_rationale(self):
        for field in ("decision_question", "missing_information", "why_needed", "expected_impact"):
            for value in (None, " "):
                self.inputs.clear()
                plan = self.generate("", "{}")
                if value is None:
                    del plan["requests"][0][field]
                else:
                    plan["requests"][0][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    SupplementPlan.model_validate(plan)

    async def test_no_registered_work_keeps_old_path(self):
        await self.run_service(supplements=[], generate=mock_generate)
        self.assertEqual(repository.list_supplement_events("test", db_path=self.path), [])
        self.assertEqual(len(repository.list_agent_results("test", db_path=self.path)), 3)

    async def test_no_data_preserves_unanswered_question(self):
        def empty_agent(agent_id):
            async def analyze(task):
                return {
                    "request_id": task.request_id,
                    "agent_id": agent_id,
                    "status": "no_data",
                    "scope": {"area": "시험 지역", "period": "시험 기간"},
                }

            return analyze

        async def fail(task, previous):
            raise RuntimeError("보완 실패")

        result = await self.run_service(
            agents={key: empty_agent(key) for key in mock_agents()},
            supplements=[self.tool(execute=fail)],
        )
        self.assertEqual(result.status, "no_data")
        self.assertEqual(len(self.inputs), 1)
        self.assertTrue(any("직장인 수요" in text for text in result.limitations))

    async def test_second_supplement_is_rejected_without_execution(self):
        def repeated(prompt, payload):
            self.inputs.clear()
            return self.generate(prompt, payload)

        with self.assertRaises(ValueError):
            await self.run_service(generate=repeated)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(repository.get_request("test", db_path=self.path)["status"], "failed")

    async def test_wrong_id_stops_before_final_decision(self):
        async def invalid(task, previous):
            previous.request_id = "other"
            return previous

        with self.assertRaises(ValueError):
            await self.run_service(supplements=[self.tool(execute=invalid)])
        self.assertEqual(len(self.inputs), 1)
        self.assertEqual(len(repository.list_agent_results("test", db_path=self.path)), 3)

    async def test_unregistered_operation_is_recorded_without_execution(self):
        def choose(prompt, payload):
            output = self.generate(prompt, payload)
            if output.get("action") == "supplement":
                output["requests"][0]["operation"] = "unknown"
            return output

        result = await self.run_service(generate=choose)
        self.assertEqual(self.calls, [])
        self.assertEqual(result.status, "partial")
        events = repository.list_supplement_events("test", db_path=self.path)
        self.assertEqual([e["status"] for e in events], ["requested", "rejected"])
        self.assertEqual(self.inputs[1]["supplement_context"][0]["status"], "rejected")

    async def test_ineligible_work_is_not_offered(self):
        def final(prompt, payload):
            self.assertNotIn("supplement_operations", json.loads(payload))
            return mock_generate(prompt, payload)

        await self.run_service(
            supplements=[self.tool(eligible=lambda task, source: False)], generate=final
        )
        self.assertEqual(self.calls, [])
        self.assertEqual(repository.list_supplement_events("test", db_path=self.path), [])

    async def test_timeout_keeps_original(self):
        async def slow(task, source):
            await asyncio.Event().wait()

        result = await self.run_service(supplements=[self.tool(execute=slow)], agent_timeout=0.05)
        self.assertEqual(result.source_analyses[0].data["office_worker_share"], 0.41)
        event = json.loads(
            repository.list_supplement_events("test", db_path=self.path)[-1]["event_json"]
        )
        self.assertEqual(event["analysis"]["error"]["code"], "SUPPLEMENT_TIMEOUT")

    async def test_storage_failure_rolls_back_candidate(self):
        initialize(self.path)
        with connect(self.path) as db:
            db.execute("""CREATE TRIGGER reject_supplement BEFORE INSERT ON supplement_events
                WHEN NEW.status = 'succeeded'
                BEGIN SELECT RAISE(ABORT, '저장 실패'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            await self.run_service()
        self.assertEqual(len(self.inputs), 1)
        self.assertEqual(len(repository.list_agent_results("test", db_path=self.path)), 3)
        self.assertEqual(repository.list_decision_results("test", db_path=self.path), [])

    async def test_duplicate_targets_and_extra_arguments_are_rejected(self):
        for extra in (False, True):

            def invalid(prompt, payload, extra=extra):
                self.inputs.clear()
                output = self.generate(prompt, payload)
                if extra:
                    output["requests"][0]["radius_m"] = 1000
                else:
                    output["requests"] *= 2
                return output

            with self.subTest(extra=extra), self.assertRaises(ValueError):
                await self.run_service(request_id=str(extra), generate=invalid)
        self.assertEqual(self.calls, [])

    async def test_partial_candidate_does_not_replace_usable_source(self):
        async def partial_result(task, previous):
            previous.status = "partial"
            previous.data = {"only_one_field": 1}
            return previous

        result = await self.run_service(supplements=[self.tool(execute=partial_result)])
        self.assertIn("office_worker_share", result.source_analyses[0].data)
        rows = repository.list_agent_results("test", db_path=self.path)
        self.assertEqual(len(rows), 4)
        event = json.loads(
            repository.list_supplement_events("test", db_path=self.path)[-1]["event_json"]
        )
        self.assertFalse(event["adopted"])

    async def test_cancellation_preserves_requested_event(self):
        entered = asyncio.Event()

        async def waiting(task, previous):
            entered.set()
            await asyncio.Event().wait()

        running = asyncio.create_task(self.run_service(supplements=[self.tool(execute=waiting)]))
        await asyncio.wait_for(entered.wait(), 2)
        running.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await running
        row = repository.get_request("test", db_path=self.path)
        self.assertEqual(json.loads(row["error_json"])["code"], "ANALYSIS_CANCELLED")
        self.assertEqual(len(repository.list_agent_results("test", db_path=self.path)), 3)
        self.assertEqual(
            repository.list_supplement_events("test", db_path=self.path)[0]["status"], "requested"
        )

    async def test_verified_addition_adopts_without_changing_original(self):
        async def added(task, previous):
            previous.data["detail"] = {"observed": 0}
            return previous

        tool = replace(self.tool(execute=added), accept=lambda old, new: "detail" in new.data)
        result = await self.run_service(supplements=[tool])
        self.assertEqual(result.source_analyses[0].data["detail"], {"observed": 0})
        self.assertTrue(self.inputs[1]["supplement_context"][0]["adopted"])

    async def test_addition_cannot_overwrite_original_even_when_callback_accepts(self):
        tool = replace(self.tool(), accept=lambda old, new: True)
        result = await self.run_service(supplements=[tool])
        self.assertEqual(result.source_analyses[0].data["office_worker_share"], 0.41)
        self.assertFalse(self.inputs[1]["supplement_context"][0]["adopted"])

    async def test_llm_parser_accepts_internal_plan(self):
        output = self.generate("", "{}")
        with patch("app.agents.decision.llm.client.complete_json", return_value=output):
            parsed = await generate_decision("", "{}", settings=LLMSettings())
        self.assertIsInstance(parsed, SupplementPlan)

    async def test_new_table_initialization_preserves_old_results(self):
        await self.run_service(supplements=[], generate=mock_generate)
        with connect(self.path) as db:
            db.execute("DROP TABLE supplement_events")
        initialize(self.path)
        initialize(self.path)
        self.assertEqual(repository.get_request("test", db_path=self.path)["status"], "completed")
        self.assertEqual(len(repository.list_agent_results("test", db_path=self.path)), 3)
        self.assertEqual(repository.list_supplement_events("test", db_path=self.path), [])
