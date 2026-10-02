"""전문가 도구가 기존 자료와 외부 조회 경계를 지키는지 확인합니다."""

import asyncio
import importlib.util
import unittest
from types import SimpleNamespace

from app.agents.specialists.tools import ToolArgumentError
from app.llm.budget import BudgetStorageError
from app.mocks import mock_agents, mock_site
from app.schemas import AnalysisTask, MapObservation


class SpecialistToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_map_failure_contract(self):
        for error in (
            TimeoutError(),
            RuntimeError("외부 실패"),
            BudgetStorageError("저장 실패"),
            ValueError("계약 오류"),
            TypeError("계약 오류"),
            asyncio.CancelledError(),
        ):

            async def lookup(task, request, error=error):
                raise error

            self.context = {}
            tool = self.tools("map_analysis", map_lookup=lookup)["search_facility"]
            with self.subTest(error=type(error).__name__):
                if isinstance(
                    error, (BudgetStorageError, ValueError, TypeError, asyncio.CancelledError)
                ):
                    with self.assertRaises(type(error)):
                        await tool.execute({"code": "SW8"})
                    self.assertNotIn("map_observation", self.context)
                else:
                    await tool.execute({"code": "SW8"})
                    observed = self.context["map_observation"]
                    code = "MAP_TIMEOUT" if isinstance(error, TimeoutError) else "MAP_FAILED"
                    self.assertEqual(observed.status, "error")
                    self.assertEqual({q.error for q in observed.data.queries.values()}, {code})

    async def asyncSetUp(self):
        self.assertIsNotNone(importlib.util.find_spec("app.agents.orchestration.consult"))
        from app.agents.orchestration.consult import build_specialist_tools

        self.build = build_specialist_tools
        self.task = AnalysisTask(request_id="r", site=mock_site(), radius_m=300)
        self.analyses = [await fn(self.task) for fn in mock_agents().values()]
        self.hooks = SimpleNamespace(
            on_supplement=None, on_map_requested=None, on_map_completed=None, on_map_result=None
        )
        self.context = {}

    def tools(self, role, **kwargs):
        return self.build(
            self.task,
            role,
            analyses=self.analyses,
            supplements=[],
            map_lookup=kwargs.get("map_lookup"),
            hooks=self.hooks,
            context=self.context,
        )

    async def test_read_only_tool_preserves_paths_and_rejects_bad_codes(self):
        tools = self.tools("commercial_area")
        result = await tools["get_industry_counts"].execute({"codes": ["I201"]})
        self.assertTrue(
            any(r["path"] == "/by_middle/0/count" and r["value"] == 96 for r in result["records"])
        )
        self.assertFalse(any(r["industry_code"] == "I212" for r in result["records"]))
        with self.assertRaises(ToolArgumentError):
            await tools["get_industry_counts"].execute({"codes": ["I299"]})
        with self.assertRaises(ToolArgumentError):
            await tools["get_industry_counts"].execute({"codes": ["I201"], "radius_m": 1})
        self.assertNotIn("retry_lq_baseline", tools)
        self.assertEqual(self.tools("map_analysis"), {})

    async def test_all_read_tools_use_only_their_own_stored_source(self):
        from unittest.mock import patch

        from app.evidence import resolve_pointer

        cases = {
            "floating_population": {
                "get_summary": {},
                "get_trend": {"quarters": 4},
                "get_time_profile": {"segment": "resident"},
                "compare_seoul": {"metric": "scale_percentile"},
            },
            "business_lifecycle": {
                "get_industry_metrics": {"codes": ["I201"]},
                "compare_industries": {"codes": ["I201", "I212"]},
            },
            "commercial_area": {
                "get_industry_counts": {"codes": ["I201"]},
                "get_radius_breakdown": {"code": "I201"},
                "get_district_specialization": {},
            },
        }
        with patch(
            "httpx.AsyncClient.send", side_effect=AssertionError("외부 조회 금지")
        ) as network:
            for role, queries in cases.items():
                source = next(a for a in self.analyses if a.agent_id == role)
                for name, args in queries.items():
                    result = await self.tools(role)[name].execute(args)
                    self.assertEqual(result["scope"], source.scope.model_dump())
                    for record in result["records"]:
                        self.assertEqual(
                            record["value"], resolve_pointer(source.data, record["path"])
                        )
            network.assert_not_called()

    async def test_map_reuses_queries_and_refuses_ninth(self):
        calls = []

        async def lookup(task, plan):
            calls.append(plan)
            self.assertEqual(task.radius_m, 300)
            return MapObservation(
                request_id="r",
                observation_id=str(len(calls)),
                site=task.site,
                radius_m=300,
                queried_at="2026-09-29T00:00:00+00:00",
                master_version="test",
                status="no_data",
                data={
                    "queries": {
                        f"q{i}": {
                            "request": q,
                            "status": "ok",
                            "method": "category",
                            "category_code": q.facility_code,
                            "total_count": 0,
                        }
                        for i, q in enumerate(plan.queries, 1)
                    }
                },
            )

        tools = self.tools("map_analysis", map_lookup=lookup)
        for code in ["SW8", "SW8", "PK6", "SC4", "HP8", "PM9", "AC5", "CS2", "MT1"]:
            await tools["search_facility"].execute({"code": code})
        self.assertEqual(len(calls), 8)
        result = await tools["search_facility"].execute({"code": "BK9"})
        self.assertIn("error", result)
        self.assertEqual(len(calls), 8)
        self.assertEqual(len(self.context["map_observation"].data.queries), 8)

    async def test_supplement_does_not_replace_original_values(self):
        from app.agents.orchestration.tools import SupplementTool
        from app.schemas import SupplementOperation

        previous = self.analyses[2].model_copy(deep=True)

        async def execute(task, analysis):
            analysis.data["store_total"] = 0
            return analysis

        tool = SupplementTool(
            SupplementOperation(
                agent_id="commercial_area", operation="retry_lq_baseline", description="재조회"
            ),
            execute,
            lambda *_: True,
            lambda *_: True,
        )
        tools = self.build(
            self.task,
            "commercial_area",
            analyses=self.analyses,
            supplements=[tool],
            map_lookup=None,
            hooks=self.hooks,
            context=self.context,
        )
        result = await tools["retry_lq_baseline"].execute({})
        self.assertFalse(result["adopted"])
        self.assertEqual(self.analyses[2], previous)

    async def test_radius_tool_keeps_slice_radius(self):
        self.analyses[2].data["by_radius"] = [
            {"radius_m": 100, "top_by_count": [{"code": "I201", "count": 7}]}
        ]
        result = await self.tools("commercial_area")["get_radius_breakdown"].execute(
            {"code": "I201"}
        )
        values = {r["path"]: r["value"] for r in result["records"]}
        self.assertEqual(values["/by_radius/0/radius_m"], 100)
        self.assertEqual(values["/by_radius/0/top_by_count/0/count"], 7)

    async def test_rejected_map_targets_still_count_toward_limit(self):
        calls = []

        async def lookup(task, plan):
            calls.append(plan)
            return MapObservation(
                request_id=task.request_id,
                observation_id=str(len(calls)),
                site=task.site,
                radius_m=task.radius_m,
                queried_at="2026-09-29T00:00:00+00:00",
                master_version="test",
                status="no_data" if len(calls) == 1 else "partial",
                data={
                    "queries": {
                        f"q{i}": {
                            "request": q,
                            "status": "error" if i == 1 and len(calls) > 1 else "ok",
                            "method": "category",
                            "category_code": q.facility_code,
                            "total_count": None if i == 1 and len(calls) > 1 else 0,
                            "error": "실패" if i == 1 and len(calls) > 1 else None,
                        }
                        for i, q in enumerate(plan.queries, 1)
                    }
                },
            )

        tools = self.tools("map_analysis", map_lookup=lookup)
        for code in ["SW8", "PK6", "SC4", "HP8", "PM9", "AC5", "CS2", "MT1"]:
            await tools["search_facility"].execute({"code": code})
        result = await tools["search_facility"].execute({"code": "BK9"})
        self.assertIn("error", result)
        self.assertEqual(len(calls), 8)
        self.assertEqual(len(self.context["map_observation"].data.queries), 1)

    async def test_mapped_evidence_cannot_be_replaced_by_unmapped_result(self):
        from test_map_mapping import plan

        from app.agents.orchestration.consult import map_adoptable
        from app.industries.lookup import find

        master = find("I212")
        payload = {
            "request_id": "r",
            "observation_id": "old",
            "site": self.task.site,
            "radius_m": 300,
            "queried_at": "2026-09-29T00:00:00+00:00",
            "master_version": "test",
            "status": "ok",
            "data": {
                "queries": {
                    "q1": {
                        "request": plan().queries[0],
                        "status": "ok",
                        "method": "keyword",
                        "total_count": 1,
                        "place_ids": ["p"],
                    }
                },
                "places": {
                    "p": {
                        "name": "카페",
                        "category_name": "카페",
                        "mapping_status": "mapped",
                        "industry_code": "I212",
                        "mapping_method": "llm",
                    }
                },
                "industries": {
                    "I212": {
                        "name": master.name,
                        "major": master.major_name,
                        "place_ids": ["p"],
                        "sampled_count": 1,
                    }
                },
            },
        }
        old = MapObservation.model_validate(payload)
        payload["status"] = "partial"
        payload["data"]["industries"] = {}
        payload["data"]["places"]["p"].update(
            mapping_status="unmapped",
            industry_code=None,
            mapping_method=None,
        )
        self.assertFalse(map_adoptable(old, MapObservation.model_validate(payload)))
