"""실제 보완 함수의 조회 경계·자료 보존·채택을 외부 호출 없이 검사합니다."""

import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.agents.business_lifecycle.client import SeoulOpenAPINoDataError
from app.agents.business_lifecycle.config import Settings as LifecycleSettings
from app.agents.commercial_area.config import Settings as CommercialSettings
from app.evidence import index_paths
from app.industries.catalog import INDUSTRY_TO_SEOUL
from app.schemas import AgentAnalysis, AnalysisTask, Site


class RealSupplementTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(
            patch("socket.socket.connect", side_effect=AssertionError("외부 호출 금지"))
        )
        self.task = AnalysisTask(
            request_id="supplement",
            radius_m=300,
            site=Site(
                input_address="시험 주소", road_address="시험 주소", latitude=37.5, longitude=127.0
            ),
        )

    def previous(self, agent_id, data):
        return AgentAnalysis(
            request_id=self.task.request_id,
            agent_id=agent_id,
            status="partial",
            scope={"area": "원래 범위", "period": "20241~20244"},
            data=data,
            warnings=["기존 한계"],
        )

    async def test_lq_requeries_only_baseline_and_preserves_original(self):
        module = importlib.import_module("app.agents.commercial_area.supplement")
        previous = self.previous(
            "commercial_area",
            {
                "radius_m": 300,
                "store_total": 10,
                "lq_retryable": True,
                "by_middle": [{"code": "I201", "count": 4, "lq": None}],
            },
        )
        from test_commercial_area_agent import sample_stores

        client = AsyncMock()
        client.stores_in_radius_with_fallback.return_value = (
            sample_stores(),
            {
                "radius_m": 2000,
                "truncated": False,
                "reference_date": "20260331",
                "from_cache": True,
            },
        )
        with patch.object(module, "StoreClient", return_value=client):
            result = await module.supplement(self.task, previous, settings=CommercialSettings())
        client.stores_in_radius.assert_not_called()
        self.assertEqual(result.data["by_middle"], previous.data["by_middle"])
        self.assertNotIn("supplement_lq", previous.data)
        self.assertEqual(result.data["supplement_lq"]["baseline_reference_date"], "20260331")
        self.assertIs(result.data["supplement_lq"]["from_cache"], True)
        self.assertAlmostEqual(
            result.data["supplement_lq"]["industries"][0]["lq"], 0.6667, places=4
        )
        self.assertTrue(module.accept(previous, result))
        self.assertNotIn("/supplement_lq/industries/0/lq", index_paths(result.data))
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.scope, previous.scope)
        client.aclose.assert_awaited_once()

        previous.data["by_middle"][0]["count"] = 5
        with patch.object(module, "StoreClient", return_value=client):
            boundary = await module.supplement(self.task, previous, settings=CommercialSettings())
        self.assertIn("/supplement_lq/industries/0/lq", index_paths(boundary.data))

    async def test_quarter_details_keep_zero_missing_and_scores_separate(self):
        module = importlib.import_module("app.agents.business_lifecycle.supplement")
        previous = self.previous(
            "business_lifecycle",
            {
                "metadata": {"area_code": "test-area", "base_quarter": "20244", "quarter_count": 4},
                "industries": [
                    {
                        "industry_id": "I201",
                        "score": 72,
                        "confidence": "none",
                        "metrics": {"period_open_count": None, "period_close_count": None},
                    }
                ],
            },
        )
        rows = [
            {
                "stdr_yyqu_cd": "20244",
                "trdar_cd": "test-area",
                "svc_induty_cd": source,
                "similr_induty_stor_co": 10,
                "opbiz_stor_co": 0,
                "clsbiz_stor_co": 1,
            }
            for source in INDUSTRY_TO_SEOUL["I201"]
        ]
        with patch(
            "app.agents.business_lifecycle.preprocess.fetch_recent_store_data", return_value=rows
        ) as fetch:
            result = await module.supplement(self.task, previous, settings=LifecycleSettings())
        self.assertEqual(fetch.call_args.kwargs["quarter_count"], 4)
        self.assertEqual(fetch.call_args.kwargs["area_code"], "test-area")
        detail = result.data["supplement_quarters"]
        self.assertEqual(detail["quarters"], ["20241", "20242", "20243", "20244"])
        entry = next(row for row in detail["industries"] if row["industry_id"] == "I201")
        self.assertIsNone(entry["opened_counts"][0])
        self.assertEqual(entry["opened_counts"][-1], 0)
        self.assertEqual(result.data["industries"], previous.data["industries"])
        self.assertTrue(module.accept(previous, result))

        self.assertEqual(entry["confidence"], "none")
        self.assertNotIn(
            "/supplement_quarters/industries/0/closed_counts/3", index_paths(result.data)
        )
        changed = result.model_copy(deep=True)
        changed.data["supplement_quarters"]["industries"][0]["confidence"] = "high"
        self.assertFalse(module.accept(previous, changed))

    def test_quarter_totals_must_match_original_metrics(self):
        module = importlib.import_module("app.agents.business_lifecycle.supplement")
        previous = self.previous(
            "business_lifecycle",
            {
                "metadata": {"area_code": "test-area", "base_quarter": "20244", "quarter_count": 2},
                "industries": [
                    {
                        "industry_id": "I201",
                        "confidence": "low",
                        "metrics": {
                            "period_open_count": 3,
                            "period_close_count": 1,
                            "period_net_change": 2,
                            "latest_store_count": 10,
                            "avg_store_count": 9,
                        },
                    }
                ],
            },
        )
        candidate = previous.model_copy(deep=True)
        candidate.data["supplement_quarters"] = {
            "area_code": "test-area",
            "quarters": ["20243", "20244"],
            "industries": [
                {
                    "industry_id": "I201",
                    "confidence": "low",
                    "store_counts": [8, 10],
                    "opened_counts": [1, 2],
                    "closed_counts": [0, 1],
                    "close_rates": [0, 10],
                }
            ],
        }
        self.assertTrue(module.accept(previous, candidate))
        for field, values in (
            ("opened_counts", [1, 3]),
            ("closed_counts", [None, 1]),
            ("store_counts", [8, 11]),
            ("close_rates", [0, 50]),
        ):
            changed = candidate.model_copy(deep=True)
            changed.data["supplement_quarters"]["industries"][0][field] = values
            with self.subTest(field=field):
                self.assertFalse(module.accept(previous, changed))

    def test_recent_totals_exclude_fifth_oldest_quarter(self):
        module = importlib.import_module("app.agents.business_lifecycle.supplement")
        previous = self.previous(
            "business_lifecycle",
            {
                "metadata": {"area_code": "test-area", "base_quarter": "20251", "quarter_count": 5},
                "industries": [
                    {
                        "industry_id": "I201",
                        "confidence": "low",
                        "metrics": {
                            "period_open_count": 104,
                            "period_close_count": 24,
                            "recent_year_open_count": 4,
                            "recent_year_close_count": 4,
                            "recent_year_net_change": 0,
                        },
                    }
                ],
            },
        )
        candidate = previous.model_copy(deep=True)
        candidate.data["supplement_quarters"] = {
            "area_code": "test-area",
            "quarters": ["20241", "20242", "20243", "20244", "20251"],
            "industries": [
                {
                    "industry_id": "I201",
                    "confidence": "low",
                    "store_counts": [100] * 5,
                    "opened_counts": [100, 1, 1, 1, 1],
                    "closed_counts": [20, 1, 1, 1, 1],
                    "close_rates": [20, 1, 1, 1, 1],
                }
            ],
        }
        self.assertTrue(module.accept(previous, candidate))
        previous.data["industries"][0]["metrics"]["recent_year_open_count"] = 104
        self.assertFalse(module.accept(previous, candidate))

    async def test_empty_quarter_query_is_not_adopted(self):
        module = importlib.import_module("app.agents.business_lifecycle.supplement")
        previous = self.previous(
            "business_lifecycle",
            {
                "metadata": {"area_code": "test-area", "base_quarter": "20244", "quarter_count": 4},
                "industries": [{"industry_id": "I201", "score": 72}],
            },
        )
        with patch(
            "app.agents.business_lifecycle.preprocess.fetch_recent_store_data", return_value=[]
        ):
            with self.assertRaises(SeoulOpenAPINoDataError):
                await module.supplement(self.task, previous, settings=LifecycleSettings())

    async def test_registered_real_functions_are_adopted_and_saved(self):
        from test_commercial_area_agent import sample_stores

        from app.agents.orchestration import build_supplement_tools
        from app.db import repository
        from app.mocks import mock_agents, mock_generate, mock_resolve
        from app.services.analysis import execute_analysis
        from app.services.settings import ExecutionSettings

        agents = mock_agents()

        def with_support(agent_id, original):
            async def analyze(task):
                result = await original(task)
                result.status = "partial"
                if agent_id == "commercial_area":
                    result.data.update({"radius_m": task.radius_m, "lq_retryable": True})
                else:
                    for row, code in zip(result.data["industries"], ("I201", "I212"), strict=True):
                        row["industry_id"] = code
                        row.setdefault("metrics", {}).update(
                            period_open_count=None, period_close_count=None
                        )
                    result.data["metadata"] = {
                        "area_code": "test-area",
                        "base_quarter": "20244",
                        "quarter_count": 4,
                    }
                return result

            return analyze

        for agent_id in ("commercial_area", "business_lifecycle"):
            agents[agent_id] = with_support(agent_id, agents[agent_id])
        inputs = []

        def generate(prompt, payload):
            inputs.append(json.loads(payload))
            if len(inputs) == 1:
                return {
                    "action": "supplement",
                    "requests": [
                        {
                            "agent_id": agent_id,
                            "operation": operation,
                            "decision_question": "비교 근거가 충분한가?",
                            "missing_information": "상세 비교 자료",
                            "why_needed": "후보 판단의 핵심 근거 확인",
                            "expected_impact": "추천 근거 유지 또는 보류",
                        }
                        for agent_id, operation in (
                            ("commercial_area", "retry_lq_baseline"),
                            ("business_lifecycle", "fetch_quarter_details"),
                        )
                    ],
                }
            return mock_generate(prompt, payload)

        client = AsyncMock()
        client.stores_in_radius_with_fallback.return_value = (sample_stores(), {"radius_m": 2000})
        rows = [
            {
                "stdr_yyqu_cd": "20244",
                "trdar_cd": "test-area",
                "svc_induty_cd": code,
                "similr_induty_stor_co": 10,
                "opbiz_stor_co": 0,
                "clsbiz_stor_co": 1,
            }
            for code in INDUSTRY_TO_SEOUL["I201"]
        ]
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("app.agents.commercial_area.supplement.StoreClient", return_value=client),
            patch(
                "app.agents.business_lifecycle.preprocess.fetch_recent_store_data",
                return_value=rows,
            ),
        ):
            path = Path(temporary) / "test.sqlite3"
            settings = ExecutionSettings()
            result = await execute_analysis(
                "시험 주소",
                request_id="real-work",
                radius_m=300,
                db_path=path,
                resolve=mock_resolve,
                agents=agents,
                generate=generate,
                settings=settings,
                supplements=build_supplement_tools(settings),
            )
            events = repository.list_supplement_events("real-work", db_path=path)
            self.assertEqual([e["status"] for e in events], ["requested", "succeeded"] * 2)
            self.assertTrue(all(e["adopted"] for e in inputs[1]["supplement_context"]))
            self.assertEqual(len(repository.list_agent_results("real-work", db_path=path)), 5)
            self.assertEqual(result.status, "partial")
