"""외부 호출 없이 서비스의 저장 시점과 실패 보존을 검증합니다."""

import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from test_orchestration_react import action

from app.db import repository as repo
from app.db.connection import initialize
from app.schemas import AGENT_IDS, AgentAnalysis, Scope, Site
from app.services.analysis import execute_analysis


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
                        "category": {"major": "음식점", "middle": "중식"},
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

    async def run_service(self, *, agents=None, request_id="request"):
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
        )

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
