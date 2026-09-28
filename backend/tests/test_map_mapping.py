"""검색 표본 매핑을 실제 조회 계층과 함께 검증합니다."""

import json
import unittest

import httpx

from app.agents.map_analysis import agent
from app.agents.map_analysis.client import PlaceClient
from app.agents.map_analysis.config import Settings
from app.schemas import AnalysisTask, MapLookupPlan, Site


def task():
    return AnalysisTask(
        request_id="map-test",
        radius_m=300,
        site=Site(
            input_address="가상 주소", road_address="가상 주소", latitude=37.5, longitude=127.03
        ),
    )


def plan():
    return MapLookupPlan(
        action="map_lookup",
        queries=[
            {
                "kind": "industry",
                "industry_code": "I212",
                "query": "카페",
                "why_needed": "경쟁",
                "expected_impact": "순위",
            }
        ],
    )


def payload():
    return {
        "meta": {"total_count": 80, "is_end": False},
        "documents": [
            {
                "id": "123",
                "place_name": "가상 점포",
                "category_name": "음식점 > 중식",
                "category_group_code": "FD6",
                "distance": "12",
                "place_url": "https://example.com/123",
            }
        ],
    }


async def mapper(prompt, raw):
    data = json.loads(raw)
    return {
        key: {"status": "mapped", "industry_code": "I202", "reason": "원본 중식 분류"}
        for key in data["categories"]
    }


class MapMappingTests(unittest.IsolatedAsyncioTestCase):
    async def test_malformed_place_does_not_discard_valid_sibling(self):
        data = payload()
        data["documents"].append(dict(data["documents"][0], id="broken", place_name=123))
        result = await self.observe(data)
        self.assertEqual(result.status, "partial")
        self.assertEqual(set(result.data.places), {"123"})
        self.assertEqual(result.data.industries["I202"].sampled_count, 1)

    async def test_empty_category_is_not_sent_to_mapper(self):
        data = payload()
        data["documents"][0]["category_name"] = ""
        data["documents"][0]["category_group_code"] = ""
        result = await self.observe(data)
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.data.places["123"].mapping_status, "unmapped")
        self.assertEqual(result.data.industries, {})

    async def test_duplicate_raw_mapping_keys_are_rejected(self):
        from unittest.mock import AsyncMock, patch

        from openai.types.chat import ChatCompletionMessage

        from app.agents.map_analysis.mapping import map_categories
        from app.llm.client import LLMResponseError
        from app.llm.config import LLMSettings

        value = (
            '{"c1":{"status":"mapped","industry_code":"I202","reason":"분류"},'
            '"c1":{"status":"mapped","industry_code":"I212","reason":"충돌"}}'
        )
        with (
            patch(
                "app.llm.client._complete",
                AsyncMock(return_value=ChatCompletionMessage(role="assistant", content=value)),
            ),
            self.assertRaises(LLMResponseError),
        ):
            await map_categories({"c1": {"name": "중식", "code": "FD6"}}, settings=LLMSettings())

    async def observe(self, response, request=None, generate=mapper):
        self.assertTrue(hasattr(agent, "observe"))

        def handle(req):
            self.assertEqual(req.url.params["radius"], "300")
            return httpx.Response(200, json=response)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            client = PlaceClient(Settings(api_key="fake"), http)
            return await agent.observe(
                task(), request or plan(), client=client, generate_mapping=generate
            )

    async def test_maps_actual_category_and_deduplicates(self):
        request = plan()
        request.queries.append(request.queries[0].model_copy(update={"query": "커피"}))
        result = await self.observe(payload(), request)
        self.assertEqual(len(result.data.places), 1)
        self.assertEqual(result.data.industries["I202"].sampled_count, 1)
        self.assertNotIn("I212", result.data.industries)
        self.assertEqual(result.data.queries["q1"].total_count, 80)
        self.assertTrue(result.data.queries["q1"].has_more)

    async def test_mapping_failure_preserves_places(self):
        async def invalid(*args):
            return {"invented": {"status": "mapped", "industry_code": "BAD"}}

        result = await self.observe(payload(), generate=invalid)
        self.assertEqual(result.status, "partial")
        self.assertEqual(len(result.data.places), 1)
        self.assertEqual(result.data.industries, {})

    async def test_zero_does_not_call_mapping(self):
        async def forbidden(*args):
            self.fail("빈 자료를 매핑하면 안 됩니다.")

        result = await self.observe(
            {"meta": {"total_count": 0, "is_end": True}, "documents": []}, generate=forbidden
        )
        self.assertEqual(result.status, "no_data")
        self.assertEqual(result.data.queries["q1"].total_count, 0)

    async def test_infrastructure_stays_unmapped(self):
        async def forbidden(*args):
            self.fail("시설을 업종에 매핑하면 안 됩니다.")

        request = MapLookupPlan(
            action="map_lookup",
            queries=[
                {
                    "kind": "infrastructure",
                    "facility_code": "SW8",
                    "why_needed": "교통",
                    "expected_impact": "수요",
                }
            ],
        )
        result = await self.observe(payload(), request, forbidden)
        self.assertEqual(result.data.places["123"].mapping_status, "not_applicable")
        self.assertEqual(result.data.industries, {})

    def test_invalid_settings_are_rejected(self):
        for values in ({"sample_size": 16}, {"max_concurrency": 0}, {"max_retries": -1}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Settings(**values)

    async def test_conflicting_place_category_is_not_counted(self):
        data = payload()
        other = dict(data["documents"][0], category_name="음식점 > 카페")
        data["documents"].append(other)
        result = await self.observe(data)
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.data.places["123"].mapping_status, "ambiguous")
        self.assertEqual(result.data.industries, {})

    async def test_failed_and_empty_search_are_distinct(self):
        request = plan()
        request.queries.append(request.queries[0].model_copy(update={"query": "커피"}))

        def handle(req):
            if req.url.params["query"] == "카페":
                return httpx.Response(401)
            return httpx.Response(200, json={"meta": {"total_count": 0}, "documents": []})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            result = await agent.observe(
                task(),
                request,
                client=PlaceClient(Settings(api_key="fake"), http),
                generate_mapping=mapper,
            )
        self.assertEqual(result.status, "partial")
        self.assertIsNone(result.data.queries["q1"].total_count)
        self.assertEqual(result.data.queries["q2"].total_count, 0)

    async def test_invalid_radius_never_connects(self):
        from unittest.mock import patch

        invalid = task().model_copy(update={"radius_m": 20_001})
        with patch("httpx.AsyncClient.send", side_effect=AssertionError("네트워크 금지")):
            result = await agent.observe(invalid, plan(), settings=Settings(api_key="fake"))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.radius_m, 20_001)
