"""원본 API 목업에서 실제 계산과 최종판단 연결을 검사합니다."""

import copy
import importlib
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from test_orchestration_react import action

from app.agents.floating_population.llm import SELECTABLE
from app.schemas import DecisionResult
from examples import run_api_mock

commercial_agent = importlib.import_module("app.agents.commercial_area.agent")


class ApiMockTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture = json.loads(run_api_mock.DEFAULT_INPUT.read_text(encoding="utf-8"))
        self.original = copy.deepcopy(self.fixture)
        self.network = self.enterContext(
            patch(
                "socket.socket.connect",
                side_effect=AssertionError("외부 연결 금지"),
            )
        )
        self.enterContext(
            patch.dict(
                os.environ,
                {
                    "ELICE_API_KEY": "test-key",
                    "ELICE_MODEL": "test-model",
                    "ELICE_BASE_URL": "https://invalid.example/v1",
                    "COMMERCIAL_AREA_API_KEY": "must-not-use",
                    "FLOATING_POPULATION_API_KEY": "must-not-use",
                    "FRANCHISE_API_KEY": "must-not-use",
                },
            )
        )
        self.select = self.enterContext(
            patch(
                "app.agents.floating_population.llm.select_blocks",
                new=AsyncMock(return_value=(list(SELECTABLE), "목업 전체 자료 유지")),
            )
        )
        self.summary = self.enterContext(
            patch.object(
                commercial_agent,
                "summarize",
                new=AsyncMock(return_value=(None, None)),
            )
        )
        self.choose = self.enterContext(
            patch(
                "app.agents.orchestration.llm.generate_action",
                new=AsyncMock(
                    side_effect=[
                        action("prepare_address"),
                        action("run_analyses"),
                        action("make_decision"),
                    ]
                ),
            )
        )
        self.generate = self.enterContext(
            patch(
                "app.agents.decision.agent.generate_decision",
                new=AsyncMock(side_effect=self.decision),
            )
        )

    def tearDown(self):
        self.network.assert_not_called()
        if self.summary.await_args:
            self.assertFalse(self.summary.await_args.args[1].cache_dir.exists())

    @staticmethod
    def decision(prompt, input_json):
        return {
            "status": "ok",
            "summary": "가상 자료 기반 연결 시험입니다.",
            "recommendations": [
                {
                    "category": {"major": "음식점", "middle": "중식"},
                    "score": 60,
                    "reasons": ["가상 유동인구와 점포 집계가 있습니다."],
                    "risks": [],
                    "evidence": [
                        {"agent_id": "floating_population", "path": "/population/daily_avg"},
                        {"agent_id": "commercial_area", "path": "/store_total"},
                    ],
                }
            ],
            "not_recommended": [],
            "limitations": [],
        }

    async def test_raw_responses_produce_calculated_results(self):
        result = await run_api_mock.run(self.fixture)
        DecisionResult.model_validate(result)
        sources = {a.agent_id: a for a in result.source_analyses}
        population = sources["floating_population"]
        commercial = sources["commercial_area"]
        self.assertEqual(population.data["population"]["daily_avg"], 10000)
        self.assertEqual(len(population.data["trend"]["quarters"]), 2)
        self.assertEqual(commercial.data["store_total"], 6)
        self.assertEqual(commercial.data["lq_baseline"]["store_total"], 10)
        self.assertEqual(commercial.data["district_baseline"]["store_total"], 12)
        self.assertEqual(commercial.data["franchise"]["count"], 1)
        self.assertEqual(sources["business_lifecycle"].error.code, "AGENT_NOT_CONNECTED")
        self.assertEqual(result.status, "partial")
        self.assertTrue(any("가상 분석" in line for line in result.limitations))
        self.select.assert_awaited_once()
        self.summary.assert_awaited_once()
        self.generate.assert_awaited_once()
        self.assertEqual(self.choose.await_count, 3)
        self.assertEqual(self.fixture, self.original)
        settings = self.summary.await_args.args[1]
        self.assertEqual(settings.llm_api_key, "test-key")

    async def test_changed_raw_input_changes_calculation(self):
        record = self.fixture["responses"]["population"]["20262"]["VwsmTrdarFlpopQq"]["row"][0]
        for key in record:
            if key.endswith("_CO"):
                record[key] *= 2
        result = await run_api_mock.run(self.fixture)
        self.assertEqual(result.source_analyses[0].data["population"]["daily_avg"], 20000)

    async def test_unknown_request_is_rejected_without_network(self):
        async with httpx.AsyncClient(transport=run_api_mock.mock_transport(self.fixture)) as client:
            with self.assertRaisesRegex(ValueError, "등록되지 않은"):
                await client.get("https://invalid.example/data")

    async def test_empty_data_skips_decision_generation(self):
        payload = self.fixture["responses"]["stores_500"]["response"]["body"]
        payload.update(items=[], totalCount=0)
        self.fixture["responses"]["areas"]["TbgisTrdarRelm"].update(row=[], list_total_count=0)
        result = await run_api_mock.run(self.fixture)
        self.assertEqual(result.status, "no_data")
        self.assertEqual(result.recommendations, [])
        self.generate.assert_not_called()
        self.select.assert_not_called()
        self.summary.assert_not_called()
