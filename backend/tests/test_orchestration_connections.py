"""실제 분석 함수의 계산과 전달을 외부 호출 없이 검증합니다."""

import asyncio
import importlib
import json
import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from test_orchestration_react import action
from test_orchestrator_e2e import MASTER, sample_stores

from app.agents.business_lifecycle.area_resolver import BusinessAreaNoDataError
from app.agents.orchestration import build_react_agents, workflow
from app.schemas import AGENT_IDS, AgentAnalysis, AnalysisTask, DecisionResult, Scope, Site

floating = importlib.import_module("app.agents.floating_population.agent")
commercial = importlib.import_module("app.agents.commercial_area.agent")
lifecycle = importlib.import_module("app.agents.business_lifecycle.agent")


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tempfile.gettempdir()
        # 계산 시험용 좌표이며 실제 개롱역 위치를 검증한 값이 아닙니다.
        self.site = Site(
            input_address="개롱역 올리브영 건물 시험 주소",
            road_address="시험 도로 123",
            detail_address="3층 302호",
            latitude=37.5,
            longitude=127.1,
        )
        self.task = AnalysisTask(request_id="connection-test", site=self.site)
        self.enterContext(
            patch.object(
                lifecycle, "resolve_area", side_effect=BusinessAreaNoDataError("시험 자료 없음")
            )
        )
        self.network = self.enterContext(
            patch(
                "httpx.AsyncClient.send",
                side_effect=AssertionError("외부 연결 금지"),
            )
        )
        self.enterContext(
            patch("socket.create_connection", side_effect=AssertionError("외부 연결 금지"))
        )
        self.enterContext(
            patch.dict(
                os.environ,
                {
                    "ELICE_API_KEY": "test-key",
                    "ELICE_BASE_URL": "https://invalid.example/v1",
                    "ELICE_MODEL": "test-model",
                    "FLOATING_POPULATION_API_KEY": "test-key",
                    "COMMERCIAL_AREA_API_KEY": "test-key",
                },
                clear=True,
            )
        )

    def tearDown(self):
        self.network.assert_not_called()
        if hasattr(self, "environment_loader"):
            self.environment_loader.assert_not_called()

    async def run_react(self, agents, generate):
        return await workflow.run_react(
            self.site.input_address,
            resolve=AsyncMock(return_value=self.site),
            agents=agents,
            generate=generate,
            request_id=self.task.request_id,
            generate_action=AsyncMock(
                side_effect=[
                    action("prepare_address"),
                    action("run_analyses"),
                    action("make_decision"),
                ]
            ),
        )

    async def test_registration_and_parallel_execution(self):
        started = set()
        ready = asyncio.Event()
        seen = []

        def make(agent_id):
            async def analyze(task, **kwargs):
                seen.append(task)
                started.add(agent_id)
                if len(started) == 3:
                    ready.set()
                await asyncio.wait_for(ready.wait(), timeout=1)
                return AgentAnalysis(
                    request_id=task.request_id,
                    agent_id=agent_id,
                    status="no_data",
                    scope=Scope(area="시험 지역", period="시험 기간"),
                )

            return AsyncMock(side_effect=analyze)

        with patch.object(
            workflow.floating_population, "analyze", make("floating_population")
        ) as fp:
            with patch.object(workflow.commercial_area, "analyze", make("commercial_area")) as ca:
                with patch(
                    "app.agents.business_lifecycle.analyze", make("business_lifecycle")
                ) as bl:
                    agents = build_react_agents()
                    self.assertEqual(set(agents), set(AGENT_IDS))
                    fp.assert_not_called()
                    ca.assert_not_called()
                    bl.assert_not_called()
                    results = await workflow.run_agents(self.task, agents)
                    self.assertTrue(all(task is self.task for task in seen))
                    self.assertEqual(len(seen), 3)
                    self.assertTrue(all(item.status == "no_data" for item in results))

    async def test_mock_coordinates_never_reach_real_functions(self):
        with patch.object(workflow.floating_population, "analyze", new_callable=AsyncMock) as fp:
            with patch.object(workflow.commercial_area, "analyze", new_callable=AsyncMock) as ca:
                task = AnalysisTask(
                    request_id="zero",
                    site=self.site.model_copy(
                        update={"latitude": 0.0, "longitude": 0.0},
                    ),
                )
                results = await workflow.run_agents(task, build_react_agents())
                self.assertEqual(
                    [r.error.code for r in results],
                    [
                        "INVALID_ANALYSIS_COORDINATES",
                        "INVALID_ANALYSIS_COORDINATES",
                        "INVALID_ANALYSIS_COORDINATES",
                    ],
                )
                fp.assert_not_called()
                ca.assert_not_called()

    def prepare_real_agents(self):
        self.environment_loader = self.enterContext(patch("app.config.load_dotenv"))
        from app.agents.floating_population.models import (
            AGE_BANDS,
            DAYS,
            TIME_BANDS,
            FlpopRecord,
            TrdarArea,
        )

        x, y = floating.to_epsg5181(self.site.latitude, self.site.longitude)
        record = FlpopRecord(
            trdar_cd="test",
            stdr_yyqu_cd="20262",
            total=42000,
            male=21000,
            female=21000,
            by_time=dict.fromkeys(TIME_BANDS, 7000.0),
            by_age=dict.fromkeys(AGE_BANDS, 7000.0),
            by_day=dict.fromkeys(DAYS, 6000.0),
        )
        fp_client = SimpleNamespace(
            fetch_trdar_areas=AsyncMock(
                return_value=[
                    TrdarArea(
                        trdar_cd="test",
                        trdar_cd_nm="가상 상권",
                        x=x,
                        y=y,
                        relm_ar=10000,
                    )
                ]
            ),
            fetch_flpop_series=AsyncMock(return_value=[("20262", [record])]),
            aclose=AsyncMock(),
        )
        meta = {"reference_date": "20260331", "radius_m": 2000}
        ca_client = SimpleNamespace(
            stores_in_radius=AsyncMock(return_value=(sample_stores(), meta)),
            stores_in_radius_with_fallback=AsyncMock(return_value=(sample_stores(), meta)),
            aclose=AsyncMock(),
        )
        for module in (floating, commercial):
            self.enterContext(
                patch.object(module.Settings, "from_env", return_value=module.Settings())
            )
        self.enterContext(patch.object(floating, "SeoulOpenDataClient", return_value=fp_client))
        self.enterContext(
            patch.object(
                floating.llm,
                "select_blocks",
                new=AsyncMock(
                    return_value=(list(floating.llm.SELECTABLE), "시험에서 모든 블록 유지"),
                ),
            )
        )
        self.enterContext(patch.object(commercial, "StoreClient", return_value=ca_client))
        self.enterContext(patch.object(commercial, "load_middle_master", return_value=MASTER))
        self.enterContext(patch.object(commercial, "load_brands", new=AsyncMock(return_value=[])))
        self.enterContext(
            patch.object(commercial, "summarize", new=AsyncMock(return_value=(None, None)))
        )
        return fp_client, ca_client

    async def test_real_calculations_reach_decision_with_missing_lifecycle(self):
        fp_client, ca_client = self.prepare_real_agents()
        captured = []

        def generate(prompt, input_json):
            captured.append(json.loads(input_json))
            return {
                "status": "ok",
                "summary": "대역 자료로 연결을 검증했습니다.",
                "recommendations": [
                    {
                        "category": {"major": "음식점업", "middle": "중식 음식점업"},
                        "score": 60,
                        "reasons": ["유동과 점포 집계를 확인했습니다."],
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

        result = await self.run_react(build_react_agents(), generate)
        DecisionResult.model_validate(result)
        self.assertEqual(result.status, "partial")
        self.assertEqual(len(result.source_analyses), 3)
        self.assertEqual(
            result.source_analyses[0].data["population"]["daily_avg"], round(42000 / 91, 1)
        )
        self.assertEqual(result.source_analyses[2].data["store_total"], 8)
        self.assertEqual(
            captured[0]["analyses"], [a.model_dump(mode="json") for a in result.source_analyses]
        )
        self.assertEqual(result.source_analyses[1].status, "no_data")
        fp_client.aclose.assert_awaited_once()
        ca_client.aclose.assert_awaited_once()

        def bad_evidence(prompt, input_json):
            content = generate(prompt, input_json)
            content["recommendations"][0]["evidence"] = [
                {"agent_id": "business_lifecycle", "path": "/industries"},
            ]
            return content

        with self.assertRaisesRegex(ValueError, "사용할 수 없는 분석"):
            await self.run_react(build_react_agents(), bad_evidence)

    async def test_three_real_analyzers_are_saved_and_lifecycle_receives_its_llm_settings(self):
        from dataclasses import replace

        from test_business_lifecycle_agent import fake_area
        from test_industry_pipeline import raw_rows

        from app.db.repository import get_request, list_agent_results
        from app.llm.config import LLMSettings
        from app.services.analysis import execute_analysis
        from app.services.settings import ExecutionSettings

        self.prepare_real_agents()
        expected_model = "lifecycle-only-model"
        settings = ExecutionSettings.from_env()
        settings = replace(
            settings,
            lifecycle=replace(
                settings.lifecycle,
                base_quarter_override="20244",
                quarter_count=4,
                api_key="captured-key",
                request_timeout_s=0.25,
            ),
            lifecycle_llm=LLMSettings(model=expected_model),
        )

        def request_page(**kwargs):
            self.assertEqual(kwargs["api_key"], "captured-key")
            self.assertEqual(kwargs["timeout"], 0.25)
            rows = [
                {key.upper(): value for key, value in row.items()}
                for row in raw_rows()
                if row["stdr_yyqu_cd"] == kwargs["quarter"]
            ]
            return {
                "VwsmTrdarStorQq": {
                    "RESULT": {"CODE": "INFO-000"},
                    "list_total_count": len(rows),
                    "row": rows,
                }
            }

        async def interpret(prompt, input_json, settings):
            self.assertEqual(settings.model, expected_model)
            payload = json.loads(input_json)
            return {
                "industry_scores": [
                    dict(item, type="안정형", evidence=[], warning=None)
                    for item in payload["industries"]
                ]
            }

        def generate(prompt, input_json):
            return {
                "status": "ok",
                "summary": "세 분석 자료 확인",
                "not_recommended": [],
                "limitations": [],
                "recommendations": [
                    {
                        "category": {"major": "음식점업", "middle": "한식 음식점업"},
                        "score": 60,
                        "reasons": ["각 분석 원본 확인"],
                        "risks": [],
                        "evidence": [{"agent_id": "business_lifecycle", "path": "/industries/0"}],
                    }
                ],
            }

        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.dict(os.environ, {"BUSINESS_LIFECYCLE_API_KEY": "later-env-key"}),
            patch.object(lifecycle, "resolve_area", new=fake_area),
            patch("app.agents.business_lifecycle.client.request_page", side_effect=request_page),
            patch("app.llm.client.complete_json", side_effect=interpret),
        ):
            path = Path(temporary) / "three.sqlite3"
            result = await execute_analysis(
                self.site.input_address,
                settings=settings,
                db_path=path,
                resolve=AsyncMock(return_value=self.site),
                generate=generate,
                generate_action=AsyncMock(
                    side_effect=[
                        action("prepare_address"),
                        action("run_analyses"),
                        action("make_decision"),
                    ]
                ),
            )
            self.assertTrue(
                all(item.status in {"ok", "partial"} for item in result.source_analyses)
            )
            self.assertEqual(len(result.source_analyses[1].data["industries"]), 75)
            snack = next(
                item
                for item in result.source_analyses[1].data["industries"]
                if item["industry_id"] == "I210"
            )
            self.assertEqual(snack["metrics"]["avg_close_rate"], 10)
            self.assertEqual(snack["score"], 55)
            self.assertEqual(len(list_agent_results(result.request_id, db_path=path)), 3)
            row = get_request(result.request_id, db_path=path)
            self.assertEqual(row["status"], "completed")
            self.assertEqual(json.loads(row["result_json"]), result.model_dump(mode="json"))

    async def test_failure_preserves_other_agent_and_no_data_skips_decision_model(self):
        self.prepare_real_agents()
        with patch.object(
            workflow.floating_population, "analyze", new=AsyncMock(side_effect=TimeoutError())
        ):
            generate = Mock(
                return_value={
                    "status": "no_data",
                    "summary": "판단 보류",
                    "recommendations": [],
                    "not_recommended": [],
                    "limitations": ["판단할 자료 부족"],
                }
            )
            result = await self.run_react(build_react_agents(), generate)
            self.assertEqual(result.source_analyses[0].error.code, "AGENT_CRASHED")
            self.assertEqual(result.source_analyses[2].data["store_total"], 8)
            self.assertEqual(result.status, "no_data")
            generate.assert_called_once()
        self.site = self.site.model_copy(update={"latitude": 0.0, "longitude": 0.0})
        generate = Mock(side_effect=AssertionError("판단 모델 호출 금지"))
        result = await self.run_react(build_react_agents(), generate)
        self.assertEqual(result.status, "no_data")
        generate.assert_not_called()

    async def test_public_errors_do_not_expose_external_details(self):
        secret = "FAKE-SECRET-KEY"

        async def crashed(task):
            raise RuntimeError(f"https://example.test/{secret}?body=private")

        result = (await workflow.run_agents(self.task, {"floating_population": crashed}))[0]
        self.assertNotIn(secret, result.model_dump_json())

        fp_client, _ = self.prepare_real_agents()
        fp_client.fetch_trdar_areas.side_effect = httpx.TimeoutException(
            f"https://example.test/?key={secret} response=private"
        )
        result = await floating.analyze(self.task)
        self.assertNotIn(secret, result.model_dump_json())

        fp_client.fetch_trdar_areas.side_effect = None
        floating.llm.select_blocks.side_effect = RuntimeError(
            f"https://example.test/?key={secret} response=private"
        )
        result = await floating.analyze(self.task)
        self.assertNotIn(secret, result.model_dump_json())

    async def test_invalid_contract_stops_both_paths_before_decision(self):
        good = AgentAnalysis(
            request_id=self.task.request_id,
            agent_id="floating_population",
            status="no_data",
            scope=Scope(area="시험 지역", period="시험 기간"),
        )
        for invalid in (
            {},
            good.model_copy(update={"request_id": "other"}),
            good.model_copy(update={"agent_id": "commercial_area"}),
        ):
            for react in (True, False):
                with self.subTest(invalid=invalid, react=react):
                    agents = build_react_agents()
                    agents["floating_population"] = AsyncMock(return_value=invalid)
                    agents["commercial_area"] = AsyncMock(
                        return_value=good.model_copy(
                            update={"agent_id": "commercial_area"},
                        )
                    )
                    generate = Mock(side_effect=AssertionError("판단 모델 호출 금지"))
                    with self.assertRaises(ValueError):
                        if react:
                            await self.run_react(agents, generate)
                        else:
                            await workflow.run_analysis(
                                self.site.input_address,
                                site=self.site,
                                agents=agents,
                                generate=generate,
                                request_id=self.task.request_id,
                            )
                    generate.assert_not_called()


class OfflineExampleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.examples = Path(__file__).resolve().parents[1] / "examples"

    async def test_offline_example_with_keys_never_connects(self):
        examples = self.examples
        with patch.dict(os.environ, {"ELICE_API_KEY": "test-key"}):
            with patch(
                "socket.socket.connect", side_effect=AssertionError("외부 연결 금지")
            ) as network:
                with patch.object(sys, "path", [str(examples), *sys.path]):
                    example = runpy.run_path(str(examples / "run_orchestration.py"))
                    with tempfile.TemporaryDirectory() as temporary:
                        path = Path(temporary) / "offline.sqlite3"
                        result = await example["run"](offline=True, db_path=path)
                        from app.db.repository import get_request

                        self.assertEqual(
                            get_request(result.request_id, db_path=path)["status"], "completed"
                        )
                DecisionResult.model_validate(result)
                network.assert_not_called()
