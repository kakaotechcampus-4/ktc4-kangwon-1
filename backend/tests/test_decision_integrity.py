"""최종판단의 공통 업종·근거 검증과 원본 보존을 검사합니다."""

import copy
import json
import unittest
from unittest.mock import AsyncMock, Mock

from app.agents.decision import analyze
from app.agents.floating_population import analyze as analyze_population
from app.agents.floating_population.config import Settings
from app.agents.floating_population.models import (
    AGE_BANDS,
    DAYS,
    TIME_BANDS,
    FlpopRecord,
    TrdarArea,
)
from app.geo import to_epsg5181
from app.industries.catalog import INDUSTRIES, INDUSTRY_MAJORS
from app.schemas import AnalysisTask, DecisionRequest, Site


class DecisionIntegrityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.request = {
            "request_id": "integrity",
            "address": "가상 시험 주소",
            "analyses": [
                {
                    "request_id": "integrity",
                    "agent_id": "floating_population",
                    "status": "ok",
                    "scope": {"area": "가상 지역", "period": "시험 기간"},
                    "data": {"value": 0},
                }
            ],
        }
        self.response = {
            "status": "ok",
            "summary": "가상 시험 판단",
            "recommendations": [
                {
                    "category": {"major": "음식점업", "middle": "한식 음식점업"},
                    "score": 50,
                    "reasons": ["시험 근거"],
                    "risks": [],
                    "evidence": [{"agent_id": "floating_population", "path": "/value"}],
                }
            ],
            "not_recommended": [],
            "limitations": [],
        }

    async def test_catalog_is_complete_in_prompt_and_all_official_categories_work(self):
        for code, name in INDUSTRIES.items():
            self.response["recommendations"][0]["category"] = {
                "major": INDUSTRY_MAJORS[code][1],
                "middle": name,
            }
            generate = Mock(return_value=self.response)
            result = await analyze(self.request, generate=generate)
            self.assertEqual(result.recommendations[0].category.middle, name)
            prompt = generate.call_args.args[0]
            self.assertTrue(code in prompt, f"공통 업종 누락: {code}")
            self.assertIn(name, prompt)

    async def test_only_existing_lookup_aliases_are_normalized(self):
        self.response["recommendations"][0]["category"]["middle"] = "한식음식점"
        result = await analyze(self.request, generate=Mock(return_value=self.response))
        self.assertEqual(result.recommendations[0].category.middle, "한식 음식점업")
        self.assertEqual(self.response["recommendations"][0]["category"]["middle"], "한식음식점")

    async def test_each_list_accepts_five_but_rejects_six_without_padding(self):
        names = [
            "한식 음식점업",
            "중식 음식점업",
            "일식 음식점업",
            "서양식 음식점업",
            "기타 간이 음식점업",
            "비알코올 음료점업",
        ]
        template = self.response["recommendations"][0]
        for target in ("recommendations", "not_recommended"):
            response = copy.deepcopy(self.response)
            response["recommendations"] = []
            response["not_recommended"] = []
            for name in names:
                item = copy.deepcopy(template)
                item["category"]["middle"] = name
                response[target].append(item)
            with self.subTest(target=target), self.assertRaises(ValueError):
                await analyze(self.request, generate=Mock(return_value=response))
            response[target].pop()
            result = await analyze(self.request, generate=Mock(return_value=response))
            self.assertEqual(len(getattr(result, target)), 5)
        result = await analyze(self.request, generate=Mock(return_value=self.response))
        self.assertEqual(len(result.recommendations), 1)
        self.assertEqual(result.not_recommended, [])

    async def test_unknown_subcategory_and_wrong_major_are_rejected(self):
        for major, middle in (
            ("음식점업", "치킨전문점"),
            ("소매업", "한식 음식점업"),
            ("음식점업", "한식 음싣점업"),
        ):
            self.response["recommendations"][0]["category"] = {"major": major, "middle": middle}
            with self.subTest(major=major, middle=middle), self.assertRaises(ValueError):
                await analyze(self.request, generate=Mock(return_value=self.response))

    async def test_aliases_cannot_duplicate_a_code_across_either_list(self):
        alias = copy.deepcopy(self.response["recommendations"][0])
        alias["category"]["middle"] = "한식음식점"
        for target in ("recommendations", "not_recommended"):
            response = copy.deepcopy(self.response)
            response[target].append(alias)
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "중복|여러 번"):
                await analyze(self.request, generate=Mock(return_value=response))

    async def test_empty_evidence_is_rejected_but_zero_and_false_are_preserved(self):
        for value in (None, "", "  ", [], {}):
            self.request["analyses"][0]["data"]["value"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "빈|비어"):
                await analyze(self.request, generate=Mock(return_value=self.response))
        for value in (0, 0.0, False):
            self.request["analyses"][0]["data"]["value"] = value
            result = await analyze(self.request, generate=Mock(return_value=self.response))
            self.assertEqual(result.source_analyses[0].data["value"], value)

    async def test_reduction_keeps_originals_and_retained_array_indices(self):
        data = self.request["analyses"][0]["data"]
        data.update(
            {
                "selection": {
                    "applied": True,
                    "included": ["trend"],
                    "dropped": ["trade_areas", "population_raw", "radius_profile"],
                },
                "trade_areas": [{"name": "가상 상권"}],
                "population": {
                    "daily_avg": 12,
                    "by_age": {"20": 9},
                    "by_day": {"mon": 0},
                    "by_time": {"11_14": 8},
                },
                "radius_profile": {"points": [{"daily_avg": 1}]},
                "trend": {"quarters": [{"value": None}, {"value": 0}, {"value": 30}]},
            }
        )
        self.response["recommendations"][0]["evidence"][0]["path"] = "/trend/quarters/1/value"
        before = copy.deepcopy(self.request)
        generate = Mock(return_value=self.response)
        result = await analyze(DecisionRequest.model_validate(self.request), generate=generate)
        sent = json.loads(generate.call_args.args[1])["analyses"][0]["data"]
        self.assertNotIn("trade_areas", sent)
        self.assertNotIn("radius_profile", sent)
        self.assertEqual(sent["population"], {"daily_avg": 12})
        self.assertEqual(sent["trend"], data["trend"])
        self.assertEqual(sent["selection"], data["selection"])
        self.assertEqual(self.request, before)
        self.assertEqual(result.source_analyses[0].data, data)
        for selection in ({"applied": False, "included": []}, None):
            data["selection"] = selection
            await analyze(self.request, generate=generate)
            self.assertEqual(json.loads(generate.call_args.args[1])["analyses"][0]["data"], data)

    async def test_pointer_uses_original_array_order_not_code_or_rank(self):
        self.request["analyses"][0]["data"] = {
            "rows": [{"code": "I212", "count": 2}, {"code": "I201", "count": 0}]
        }
        self.response["recommendations"][0]["evidence"][0]["path"] = "/rows/1/count"
        await analyze(self.request, generate=Mock(return_value=self.response))
        for path in ("/rows/I201/count", "/rows/01/count", "/rows/2/count", "/rows/-1/count"):
            self.response["recommendations"][0]["evidence"][0]["path"] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                await analyze(self.request, generate=Mock(return_value=self.response))

    async def test_population_selection_returns_every_chart_for_storage(self):
        site = Site(
            input_address="가상 주소", road_address="가상 주소", latitude=37.5, longitude=127.0
        )
        x, y = to_epsg5181(site.latitude, site.longitude)
        record = FlpopRecord(
            trdar_cd="A",
            stdr_yyqu_cd="20251",
            total=600,
            male=300,
            female=300,
            by_age={k: 100 for k in AGE_BANDS},
            by_day={k: 60 for k in DAYS},
            by_time={k: 100 for k in TIME_BANDS},
        )
        client = Mock(
            fetch_trdar_areas=AsyncMock(
                return_value=[TrdarArea(trdar_cd="A", trdar_cd_nm="시험", x=x, y=y)]
            ),
            fetch_flpop_series=AsyncMock(return_value=[("20251", [record])]),
        )
        result = await analyze_population(
            AnalysisTask(request_id="integrity", site=site),
            settings=Settings(),
            client=client,
            select=AsyncMock(return_value=([], "시험 선별")),
        )
        self.assertIsNotNone(result.data["population"]["by_age"])
        self.assertEqual(result.data["population"]["by_age"]["20"], 100)
        self.assertEqual(len(result.data["trade_areas"]), 1)
        self.assertEqual(len(result.data["trend"]["quarters"]), 1)
        self.assertTrue(result.data["radius_profile"]["points"])
        self.assertTrue(result.data["selection"]["applied"])
        self.assertEqual(result.data["selection"]["included"], [])


if __name__ == "__main__":
    unittest.main()
