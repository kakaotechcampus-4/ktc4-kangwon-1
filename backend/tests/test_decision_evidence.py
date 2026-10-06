"""업종과 근거 위치를 코드로 연결하는지 검사합니다."""

import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from pydantic import ValidationError

from app.agents.business_lifecycle.formatter import format_scored_industry
from app.agents.decision.agent import DecisionContractError, evaluate
from app.evidence import index_paths
from app.industries import lookup
from app.mocks import (
    mock_agents,
    mock_business_lifecycle_data,
    mock_commercial_area_data,
    mock_generate,
    mock_site,
)
from app.schemas import AnalysisTask, DecisionRequest


def lifecycle_row(code, **fields):
    row = dict(mock_business_lifecycle_data()["industries"][0])
    row.update(industry_id=code, industry_name=lookup.get(code).name, **fields)
    return row


def lifecycle_data(*rows):
    return {**mock_business_lifecycle_data(), "industries": list(rows)}


class EvidenceTests(unittest.IsolatedAsyncioTestCase):
    def test_renamed_or_unregistered_industry_rows_are_not_guessed(self):
        data = mock_business_lifecycle_data()
        renamed = json.loads(json.dumps(data))
        renamed["industries"][0]["upjong_code"] = renamed["industries"][0].pop("industry_id")
        with self.assertRaises(ValidationError):
            index_paths(renamed, "business_lifecycle")
        extra = {**data, "top_industries": [{"upjong_code": "I201", "store_count": 12}]}
        with self.assertRaises(ValidationError):
            index_paths(extra, "business_lifecycle")

    async def test_invalid_category_is_corrected_at_both_model_boundaries(self):
        for category in (
            {"code": "I299"},
            {"code": "I201", "major": "음식점업", "middle": "한식 음식점업 "},
            {"code": "I201", "major": "다른 분류", "middle": "한식 음식점업"},
        ):
            for real_model in (False, True):
                bad = self.response("/industries/1/metrics/net")
                bad["recommendations"][0]["category"] = category
                good = self.response("/industries/1/metrics/net")
                call = AsyncMock(side_effect=[bad, good])
                with self.subTest(category=category, real_model=real_model):
                    if real_model:
                        with patch("app.llm.client.complete_json", call):
                            result = await evaluate(self.request)
                    else:
                        result = await evaluate(self.request, generate=call)
                    self.assertEqual(result.recommendations[0].category.code, "I201")
                    correction = json.loads(call.call_args_list[1].args[1])["correction"]
                    self.assertEqual(correction["reason"], "invalid_category")
                    self.assertEqual(correction["field"], "recommendations.0.category")

    async def test_repeated_invalid_code_stops_after_one_correction(self):
        bad = self.response("/industries/1/metrics/net")
        bad["recommendations"][0]["category"] = {"code": "I299"}
        call = AsyncMock(return_value=bad)
        with patch("app.llm.client.complete_json", call):
            with self.assertRaises(DecisionContractError) as raised:
                await evaluate(self.request)
        self.assertEqual(call.await_count, 2)
        self.assertEqual(len(raised.exception.failures), 2)

    def test_lifecycle_rule_describes_counts_without_changing_metrics(self):
        from app.agents.business_lifecycle.formatter import describe_industry

        for opened, closed, label in (
            (3, 1, "개업 우위"),
            (1, 3, "폐업 우위"),
            (2, 2, "개폐업 균형"),
        ):
            source = {
                "lifecycle_score": 61,
                "confidence": "low",
                "metrics": {"period_open_count": opened, "period_close_count": closed},
            }
            result = describe_industry(source)
            self.assertEqual(result["type"], label)
            self.assertEqual(result["metrics"], source["metrics"])
            self.assertEqual(result["lifecycle_score"], 61)
            self.assertNotIn("type", source)

    def test_agent_sample_citation_paths(self):
        population = {"population": {"daily_avg": 120}, "resident": {"count": 0}}
        self.assertEqual(
            index_paths(population, "floating_population"),
            {
                "/population/daily_avg": None,
                "/population": None,
                "/resident/count": None,
                "/resident": None,
            },
        )
        lifecycle = lifecycle_data(
            lifecycle_row("I201", metrics={"net": 0}, type="설명", citable={"type": False})
        )
        paths = index_paths(lifecycle, "business_lifecycle")
        for path in (
            "/industries/0/industry_id",
            "/industries/0/metrics/net",
            "/industries/0/metrics",
        ):
            self.assertEqual(paths[path], "I201")
        for path in ("/industries/0/type", "/industries/0"):
            self.assertNotIn(path, paths)
        commercial = mock_commercial_area_data()
        commercial["by_middle"][0].update(count=2, lq=3.0, citable={"lq": False})
        paths = index_paths(commercial, "commercial_area")
        self.assertEqual(paths["/by_middle/0/code"], "I201")
        self.assertEqual(paths["/by_middle/0/count"], "I201")
        for path in ("/by_middle/0/lq", "/by_middle/0"):
            self.assertNotIn(path, paths)

    def test_citable_false_blocks_subtree_and_ancestors_but_keeps_siblings(self):
        data = {
            "group": {
                "observed": 0,
                "generated": {
                    "citable": False,
                    "text": "추정",
                    "nested": {"citable": True, "value": 9},
                },
            }
        }
        self.assertEqual(index_paths(data, "floating_population"), {"/group/observed": None})

    def test_field_policy_preserves_values_without_allowing_parent_citation(self):
        data = lifecycle_data(
            lifecycle_row(
                "I201",
                metrics={"net": 0},
                type="성장",
                evidence=["생성 문장"],
                citable={"type": False, "evidence": False},
            )
        )
        paths = index_paths(data, "business_lifecycle")
        self.assertIn("/industries/0/metrics/net", paths)
        for path in (
            "/industries",
            "/industries/0",
            "/industries/0/type",
            "/industries/0/evidence/0",
            "/industries/0/citable/type",
        ):
            self.assertNotIn(path, paths)

    def test_lifecycle_generated_text_is_not_evidence(self):
        row = format_scored_industry(
            {
                "industry_id": "I201",
                "industry_name": "한식 음식점업",
                "lifecycle_score": 60,
                "type": "성장",
                "confidence": "high",
                "metrics": {"net": 2},
                "evidence": ["생성 문장"],
            }
        )
        paths = index_paths(lifecycle_data(row), "business_lifecycle")
        self.assertIn("/industries/0/metrics/net", paths)
        self.assertNotIn("/industries/0/type", paths)
        self.assertNotIn("/industries/0/evidence/0", paths)

    async def test_evaluate_rejects_citable_false_including_parent(self):
        self.source.data["industries"][1]["citable"] = {"type": False}
        for path in ("/industries/1/type", "/industries/1"):
            with self.subTest(path=path), self.assertRaises(DecisionContractError):
                await evaluate(self.request, generate=Mock(return_value=self.response(path)))

    async def asyncSetUp(self):
        task = AnalysisTask(request_id="evidence", site=mock_site())
        self.request = DecisionRequest(
            request_id=task.request_id,
            address="시험",
            analyses=[await fn(task) for fn in mock_agents().values()],
        )
        self.source = next(s for s in self.request.analyses if s.agent_id == "business_lifecycle")
        self.source.data = lifecycle_data(
            lifecycle_row("S209", metrics={"net": 3}),
            lifecycle_row("I201", data_available=True, metrics={"net": 0, "missing": None}),
        )

    def response(self, path, agent_id="business_lifecycle"):
        result = mock_generate("", "")
        result["not_recommended"] = []
        result["recommendations"][0]["evidence"] = [{"agent_id": agent_id, "path": path}]
        result["recommendations"][0]["reasons"] = ["근거를 확인했습니다."]
        result["recommendations"][0]["risks"] = []
        return result

    async def test_first_call_provides_exact_paths_after_reordering(self):
        original = self.request.model_dump()
        seen = []

        def generate(prompt, payload):
            seen.append(json.loads(payload))
            return self.response("/industries/1/metrics/net")

        await evaluate(self.request, generate=generate)
        entries = seen[0].get("industry_evidence", [])
        self.assertTrue(entries, "첫 호출부터 업종별 실제 근거 경로가 필요합니다.")
        entry = next(
            e
            for e in entries
            if e["industry_code"] == "I201" and e["agent_id"] == "business_lifecycle"
        )
        self.assertIn("/industries/1/metrics/net", entry["paths"])
        self.assertNotIn("/industries/1/metrics/missing", entry["paths"])
        self.assertEqual(self.request.model_dump(), original)
        self.source.data["industries"].reverse()
        await evaluate(
            self.request, generate=Mock(return_value=self.response("/industries/0/metrics/net"))
        )

    async def test_other_industry_is_rejected_and_correction_stays_in_industry(self):
        calls = []

        def generate(prompt, payload):
            calls.append(json.loads(payload))
            return self.response("/industries/0/metrics/net")

        with self.assertRaises(DecisionContractError):
            await evaluate(self.request, generate=generate)
        candidates = calls[1]["correction"]["candidates"]
        self.assertTrue(candidates)
        self.assertTrue(
            all(
                c["path"] == "/industries/1" or c["path"].startswith("/industries/1/")
                for c in candidates
            )
        )

    async def test_missing_row_and_parent_collection_are_not_evidence(self):
        self.source.data["industries"][1]["data_available"] = False
        for path in ("/industries/1", "/industries/1/metrics/net", "/industries"):
            with self.subTest(path=path), self.assertRaises(DecisionContractError):
                await evaluate(self.request, generate=Mock(return_value=self.response(path)))

    async def test_commercial_code_and_supplement_paths_match_industry(self):
        source = next(s for s in self.request.analyses if s.agent_id == "commercial_area")
        data = mock_commercial_area_data()
        laundry = lookup.get("S209")
        data["by_middle"][0].update(
            code="S209",
            name=laundry.name,
            major_code=laundry.major_code,
            major_name=laundry.major_name,
            count=3,
        )
        data["by_middle"][1].update(
            code="I201",
            name=lookup.get("I201").name,
            major_code=lookup.get("I201").major_code,
            major_name=lookup.get("I201").major_name,
            count=0,
        )
        data["supplement_lq"] = {
            "analysis_radius_m": 500,
            "baseline_radius_m": 2000,
            "baseline_store_total": 9000,
            "checked_at": "2026-10-03T00:00:00+00:00",
            "industries": [{"industry_id": "I201", "citable": {"lq": True}, "lq": 0.0}],
            "note": "보완",
        }
        source.data = data
        for path in ("/by_middle/1/count", "/supplement_lq/industries/0/lq"):
            result = await evaluate(
                self.request, generate=Mock(return_value=self.response(path, "commercial_area"))
            )
            self.assertTrue(result.recommendations)
        with self.assertRaises(DecisionContractError):
            await evaluate(
                self.request,
                generate=Mock(return_value=self.response("/by_middle/0/count", "commercial_area")),
            )

    async def test_unknown_or_conflicting_identity_is_not_shared_evidence(self):
        for changes, error in (
            ({"industry_id": "unknown"}, ValidationError),
            ({"industry_name": lookup.get("S209").name}, ValidationError),
            ({"confidence": "none"}, DecisionContractError),
        ):
            original = self.source.data["industries"][1].copy()
            self.source.data["industries"][1].update(changes)
            with self.subTest(changes=changes), self.assertRaises(error):
                await evaluate(
                    self.request,
                    generate=Mock(return_value=self.response("/industries/1/metrics/net")),
                )
            self.source.data["industries"][1] = original

    async def test_hidden_population_block_is_not_evidence(self):
        source = next(s for s in self.request.analyses if s.agent_id == "floating_population")
        source.data.update(selection={"applied": True, "included": []}, trade_areas=[{"count": 3}])
        with self.assertRaises(DecisionContractError):
            await evaluate(
                self.request,
                generate=Mock(
                    return_value=self.response("/trade_areas/0/count", "floating_population")
                ),
            )

    async def test_area_and_major_codes_remain_shared_context(self):
        source = next(s for s in self.request.analyses if s.agent_id == "commercial_area")
        data = mock_commercial_area_data()
        data["trade_areas"] = [
            {
                "code": "3110001",
                "name": "시험 상권",
                "distance_m": 10.0,
                "area_m2": 100.0,
                "equivalent_radius_m": 5.6,
            }
        ]
        data["by_major"] = [
            {"code": "I2", "name": "음식점업", "count": 50, "share": 0.1, "density_per_km2": 9.0}
        ]
        source.data = data
        for path in ("/trade_areas/0/area_m2", "/by_major/0/count"):
            result = await evaluate(
                self.request, generate=Mock(return_value=self.response(path, "commercial_area"))
            )
            self.assertTrue(result.recommendations)
        unknown = json.loads(json.dumps(data))
        unknown["by_middle"][0]["code"] = "unknown"
        source.data = unknown
        with self.assertRaises(ValidationError):
            await evaluate(
                self.request,
                generate=Mock(return_value=self.response("/by_middle/0/count", "commercial_area")),
            )
