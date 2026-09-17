"""외부 호출 없이 서비스의 저장 시점과 실패 보존을 검증합니다."""

import asyncio
import json
import sqlite3
import tempfile
import threading
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from pydantic import ValidationError
from test_business_lifecycle_agent import fake_area
from test_industry_pipeline import raw_rows
from test_orchestration_react import action

from app.agents.business_lifecycle.agent import analyze as analyze_lifecycle
from app.agents.business_lifecycle.config import Settings as LifecycleSettings
from app.db import repository as repo
from app.db.connection import initialize
from app.schemas import AGENT_IDS, AgentAnalysis, Scope, Site
from app.services.analysis import execute_analysis
from app.services.settings import ExecutionSettings


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "service.sqlite3"
        self.site = Site(
            input_address="시험 주소", road_address="시험 도로", latitude=0.0, longitude=0.0
        )
        self.resolve = AsyncMock(return_value=self.site)
        self.generate = Mock(
            return_value={
                "status": "ok",
                "summary": "시험 판단",
                "recommendations": [
                    {
                        "category": {"major": "음식점업", "middle": "중식 음식점업"},
                        "score": 60,
                        "reasons": ["시험 자료"],
                        "risks": [],
                        "evidence": [{"agent_id": "commercial_area", "path": "/count"}],
                    }
                ],
                "not_recommended": [],
                "limitations": [],
            }
        )

    def agents(self, status="ok"):
        def make(agent_id):
            async def analyze(task):
                return AgentAnalysis(
                    request_id=task.request_id,
                    agent_id=agent_id,
                    status=status,
                    scope=Scope(area="시험 지역", period="시험 기간"),
                    data={} if status == "no_data" else {"count": 1},
                )

            return analyze

        return {agent_id: make(agent_id) for agent_id in AGENT_IDS}

    async def run_service(self, *, agents=None, request_id="request", **kwargs):
        return await execute_analysis(
            "시험 주소",
            db_path=self.path,
            resolve=self.resolve,
            agents=self.agents() if agents is None else agents,
            request_id=request_id,
            generate=self.generate,
            generate_action=AsyncMock(
                side_effect=[
                    action("prepare_address"),
                    action("run_analyses"),
                    action("make_decision"),
                ]
            ),
            **kwargs,
        )

    async def test_agent_deadline_collects_timeout_and_other_results(self):
        agents = self.agents()
        stopped = asyncio.Event()

        async def slow(task):
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        agents["floating_population"] = slow
        result = await self.run_service(agents=agents, agent_timeout=0.02)
        self.assertTrue(stopped.is_set())
        self.assertEqual(result.source_analyses[0].error.code, "AGENT_TIMEOUT")
        self.assertEqual(len(repo.list_agent_results("request", db_path=self.path)), 3)

    async def test_overall_timeout_and_cancellation_fail_owned_request(self):
        for cancel in (False, True):
            entered, stopped = asyncio.Event(), asyncio.Event()

            async def resolve(address, entered=entered, stopped=stopped):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.set()

            self.resolve.side_effect = resolve
            task = asyncio.create_task(
                self.run_service(request_id=str(cancel), overall_timeout=0.3)
            )
            await asyncio.wait_for(entered.wait(), 1)
            if cancel:
                task.cancel()
            with self.assertRaises(asyncio.CancelledError if cancel else TimeoutError):
                await task
            self.assertTrue(stopped.is_set())
            row = repo.get_request(str(cancel), db_path=self.path)
            self.assertEqual(row["status"], "failed")
            self.assertEqual(
                json.loads(row["error_json"])["code"],
                "ANALYSIS_CANCELLED" if cancel else "ANALYSIS_TIMEOUT",
            )

    async def test_cancel_waits_for_insert_or_commit_and_preserves_ownership(self):
        for operation, duplicate, expected in (
            ("create_request", False, "failed"),
            ("create_request", True, "pending"),
            ("complete_request", False, "completed"),
        ):
            request_id = f"{operation}-{duplicate}"
            if duplicate:
                initialize(self.path)
                repo.create_request(request_id, "기존 요청", db_path=self.path)
            original = getattr(repo, operation)
            entered, release = threading.Event(), threading.Event()

            def blocked(*args, entered=entered, release=release, original=original, **kwargs):
                entered.set()
                if not release.wait(3):
                    raise AssertionError("시험 쓰기 해제 시간 초과")
                return original(*args, **kwargs)

            with patch.object(repo, operation, side_effect=blocked):
                task = asyncio.create_task(self.run_service(request_id=request_id))
                self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertEqual(repo.get_request(request_id, db_path=self.path)["status"], expected)

    async def test_cancel_before_completion_write_leaves_failed_not_success(self):
        started = asyncio.Event()

        async def decision(*args):
            started.set()
            await asyncio.Event().wait()

        self.generate = decision
        task = asyncio.create_task(self.run_service())
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        row = repo.get_request("request", db_path=self.path)
        self.assertEqual(row["status"], "failed")
        self.assertIsNone(row["result_json"])

    async def test_cancel_during_failure_recording_propagates_after_write(self):
        entered, release = threading.Event(), threading.Event()
        original = repo.fail_request

        def blocked(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise AssertionError("시험 쓰기 해제 시간 초과")
            return original(*args, **kwargs)

        with (
            patch.object(
                repo, "complete_request", side_effect=sqlite3.OperationalError("시험 오류")
            ),
            patch.object(repo, "fail_request", side_effect=blocked),
        ):
            task = asyncio.create_task(self.run_service())
            self.assertTrue(await asyncio.to_thread(entered.wait, 3))
            task.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(repo.get_request("request", db_path=self.path)["status"], "failed")

    async def test_invalid_deadlines_never_create_database(self):
        for value in (0, -1, float("inf"), float("nan"), True):
            for key in ("agent_timeout", "overall_timeout"):
                with self.assertRaises(ValueError):
                    await self.run_service(**{key: value})
        self.assertFalse(self.path.exists())

    async def test_success_partial_and_no_data_are_completed(self):
        for status in ("ok", "partial", "no_data"):
            result = await self.run_service(agents=self.agents(status), request_id=status)
            row = repo.get_request(status, db_path=self.path)
            self.assertEqual(result.status, status)
            self.assertEqual(row["status"], "completed")
            history = repo.list_decision_results(status, db_path=self.path)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["result_json"], row["result_json"])
            self.assertEqual(json.loads(row["site_json"]), self.site.model_dump())
            self.assertEqual(json.loads(row["result_json"]), result.model_dump(mode="json"))
            self.assertEqual(len(repo.list_agent_results(status, db_path=self.path)), 3)

    async def test_immediate_storage_before_other_agent_finishes(self):
        agents = self.agents()
        original = agents["business_lifecycle"]

        async def slow(task):
            for _ in range(100):
                rows = await asyncio.to_thread(
                    repo.list_agent_results, task.request_id, db_path=self.path
                )
                if rows:
                    self.assertTrue(all(row["agent_id"] != "business_lifecycle" for row in rows))
                    request = repo.get_request(task.request_id, db_path=self.path)
                    self.assertEqual(request["status"], "running")
                    self.assertIsNotNone(request["site_json"])
                    return await original(task)
                await asyncio.sleep(0.01)
            self.fail("다른 분석이 끝나기 전에 결과가 저장되지 않았습니다.")

        agents["business_lifecycle"] = slow
        result = await self.run_service(agents=agents)
        self.assertEqual(result.status, "ok")

    async def test_agent_exception_is_saved_without_stopping_others(self):
        agents = self.agents()
        agents["floating_population"] = AsyncMock(side_effect=TimeoutError("시험 시간 초과"))
        result = await self.run_service(agents=agents)
        self.assertEqual(result.status, "partial")
        rows = repo.list_agent_results("request", db_path=self.path)
        failed = next(row for row in rows if row["agent_id"] == "floating_population")
        self.assertEqual(json.loads(failed["analysis_json"])["error"]["code"], "AGENT_CRASHED")
        self.assertEqual(len(rows), 3)

    async def test_completion_write_failure_never_returns_success(self):
        with patch.object(
            repo, "complete_request", side_effect=sqlite3.OperationalError("쓰기 실패")
        ):
            with self.assertRaises(sqlite3.OperationalError):
                await self.run_service()
        row = repo.get_request("request", db_path=self.path)
        self.assertEqual(row["status"], "failed")
        self.assertIsNone(row["result_json"])
        self.assertEqual(len(repo.list_agent_results("request", db_path=self.path)), 3)

    async def test_address_failure_does_not_start_agents(self):
        self.resolve.side_effect = ValueError("secret-key-must-not-be-stored")
        agents = {key: AsyncMock() for key in AGENT_IDS}
        with self.assertRaises(ValueError):
            await self.run_service(agents=agents)
        for agent in agents.values():
            agent.assert_not_called()
        row = repo.get_request("request", db_path=self.path)
        self.assertEqual(row["status"], "failed")
        self.assertNotIn("secret-key", row["error_json"])

    async def test_decision_failure_preserves_analysis_results(self):
        self.generate.side_effect = RuntimeError("모델 실패")
        with self.assertRaises(RuntimeError):
            await self.run_service()
        self.assertEqual(len(repo.list_agent_results("request", db_path=self.path)), 3)
        self.assertEqual(repo.get_request("request", db_path=self.path)["status"], "failed")

    async def test_contract_error_keeps_other_results(self):
        for invalid in (
            {},
            AgentAnalysis(
                request_id="other",
                agent_id="floating_population",
                status="no_data",
                scope=Scope(area="시험 지역", period="시험 기간"),
            ),
        ):
            agents = self.agents()
            agents["floating_population"] = AsyncMock(return_value=invalid)
            request_id = "invalid" if isinstance(invalid, dict) else "wrong-id"
            with self.assertRaises(ValueError):
                await self.run_service(agents=agents, request_id=request_id)
            rows = repo.list_agent_results(request_id, db_path=self.path)
            self.assertEqual(len(rows), 2)
            self.assertNotIn("floating_population", [r["agent_id"] for r in rows])
        self.generate.assert_not_called()

    async def test_internal_contract_error_is_not_collected_as_operational_failure(self):
        from pydantic import ValidationError

        async def invalid(task):
            return AgentAnalysis.model_validate({"request_id": task.request_id})

        agents = self.agents()
        agents["floating_population"] = invalid
        with self.assertRaises(ValidationError):
            await self.run_service(agents=agents)
        self.generate.assert_not_called()
        self.assertEqual(repo.get_request("request", db_path=self.path)["status"], "failed")
        self.assertEqual(
            {row["agent_id"] for row in repo.list_agent_results("request", db_path=self.path)},
            {"business_lifecycle", "commercial_area"},
        )

    async def test_real_lifecycle_contract_error_fails_request_and_keeps_other_results(self):
        async def completion(prompt, input_json, settings):
            payload = json.loads(input_json)
            return {
                "industry_scores": [
                    dict(row, type="안정형", evidence=[], warning=None)
                    for row in payload["industries"]
                ]
            }

        settings = ExecutionSettings(
            lifecycle=LifecycleSettings(base_quarter_override="20244", quarter_count=4)
        )
        agents = self.agents()
        agents["business_lifecycle"] = partial(
            analyze_lifecycle,
            settings=settings.lifecycle,
            llm_settings=settings.lifecycle_llm,
            area_resolver=fake_area,
        )
        with (
            patch(
                "app.agents.business_lifecycle.preprocess.fetch_recent_store_data",
                return_value=raw_rows(),
            ),
            patch("app.llm.client.complete_json", side_effect=completion),
            # 실제 계산·포맷을 통과한 공통 응답의 계약 위반을 주입합니다.
            patch(
                "app.agents.business_lifecycle.formatter.determine_status",
                return_value="invalid-status",
            ),
            self.assertRaises(ValidationError) as raised,
        ):
            await self.run_service(agents=agents, settings=settings)

        self.assertEqual(raised.exception.errors()[0]["loc"], ("status",))
        self.generate.assert_not_called()
        request = repo.get_request("request", db_path=self.path)
        self.assertEqual(request["status"], "failed")
        self.assertIsNone(request["result_json"])
        rows = repo.list_agent_results("request", db_path=self.path)
        self.assertEqual(
            {row["agent_id"] for row in rows}, {"floating_population", "commercial_area"}
        )
        for row in rows:
            analysis = json.loads(row["analysis_json"])
            self.assertEqual(analysis["status"], "ok")
            self.assertEqual(analysis["data"], {"count": 1})

    async def test_storage_failure_is_not_agent_failure(self):
        original = repo.save_agent

        def fail_one(analysis, **kwargs):
            if analysis.agent_id == "floating_population":
                raise sqlite3.OperationalError("쓰기 실패")
            original(analysis, **kwargs)

        with patch.object(repo, "save_agent", side_effect=fail_one):
            with self.assertRaises(sqlite3.OperationalError):
                await self.run_service()
        self.generate.assert_not_called()
        self.assertEqual(len(repo.list_agent_results("request", db_path=self.path)), 2)
        row = repo.get_request("request", db_path=self.path)
        self.assertEqual(json.loads(row["error_json"])["code"], "STORAGE_ERROR")
        self.assertIsNone(row["result_json"])

    async def test_concurrent_requests_and_duplicate_rejection(self):
        initialize(self.path)
        first, second = await asyncio.gather(
            self.run_service(request_id="first"),
            self.run_service(request_id="second"),
        )
        for result in (first, second):
            rows = repo.list_agent_results(result.request_id, db_path=self.path)
            self.assertEqual(len(rows), 3)
            self.assertTrue(
                all(json.loads(r["analysis_json"])["request_id"] == result.request_id for r in rows)
            )
        with self.assertRaises(sqlite3.IntegrityError):
            await self.run_service(request_id="first")
        self.assertEqual(repo.get_request("first", db_path=self.path)["status"], "completed")

    async def test_invalid_input_never_initializes_database(self):
        with patch("app.services.analysis.initialize") as init:
            for address, request_id, agents in (
                (" ", "id", self.agents()),
                ("주소", " ", self.agents()),
                ("주소", "id", {}),
            ):
                with self.assertRaises(ValueError):
                    await execute_analysis(
                        address,
                        request_id=request_id,
                        agents=agents,
                        resolve=self.resolve,
                        db_path=self.path,
                    )
            init.assert_not_called()
