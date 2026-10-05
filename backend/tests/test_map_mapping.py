"""검색 표본 매핑을 실제 조회 계층과 함께 검증합니다."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

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
                "category_name": "음식점 > 중식 > 중식당",
                "category_group_code": "FD6",
                "distance": "12",
                "place_url": "https://example.com/123",
            }
        ],
    }


async def mapper(prompt, raw):
    data = json.loads(raw)
    return {key: {"status": "same", "reason": "원본 중식 분류"} for key in data["pairs"]}


class MapMappingTests(unittest.IsolatedAsyncioTestCase):
    async def test_mapping_budget_storage_failure_is_not_partial_success(self):
        from app.llm.budget import BudgetStorageError

        async def failed(*_):
            raise BudgetStorageError("저장 실패")

        with tempfile.TemporaryDirectory() as folder:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload()))
            ) as http:
                with self.assertRaises(BudgetStorageError):
                    await agent.observe(
                        task(),
                        plan(),
                        client=PlaceClient(Settings(api_key="fake"), http),
                        generate_mapping=failed,
                        mapping_cache_path=Path(folder) / "cache.sqlite3",
                    )

    async def test_cached_mapping_plus_model_failure_is_partial_and_keeps_both_places(self):
        from unittest.mock import patch

        data = payload()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mapping.sqlite3"
            with patch.dict("os.environ", {"MAP_MAPPING_MODEL": "test"}):
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))
                ) as http:
                    client = PlaceClient(Settings(api_key="fake"), http)
                    await agent.observe(
                        task(),
                        plan(),
                        client=client,
                        generate_mapping=mapper,
                        mapping_cache_path=path,
                    )
                    data["documents"].append(
                        dict(data["documents"][0], id="456", category_name="새 분류")
                    )

                    async def failed(*args):
                        raise RuntimeError("매핑 모델 실패")

                    result = await agent.observe(
                        task(),
                        plan(),
                        client=client,
                        generate_mapping=failed,
                        mapping_cache_path=path,
                    )
        self.assertEqual(result.status, "partial")
        self.assertEqual(set(result.data.places), {"123", "456"})
        self.assertEqual(result.data.queries["q1"].matches["456"], "unclear")
        self.assertEqual(result.data.industries["I212"].sampled_count, 1)
        self.assertTrue(any("불확실" in w for w in result.warnings))

    async def test_expired_or_broken_cache_requeries_model(self):
        from contextlib import closing

        from app.agents.map_analysis.mapping import judge_matches
        from app.llm.config import LLMSettings

        calls = []

        async def generate(prompt, raw):
            calls.append(raw)
            return {"c1": {"status": "same", "reason": "중식"}}

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mapping.sqlite3"
            args = dict(generate=generate, settings=LLMSettings(model="test"), cache_path=path)
            categories = {
                "c1": {"target": {"code": "I212"}, "category": {"name": "중식", "code": "FD6"}}
            }
            await judge_matches(categories, **args)
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("UPDATE mappings SET saved=0")
            await judge_matches(categories, **args)
            path.write_bytes(b"broken cache")
            result = await judge_matches(categories, **args)
            self.assertEqual(result["c1"].status, "same")
            self.assertEqual(len(calls), 3)

    async def test_unconfirmed_mapping_is_not_cached_and_model_change_requeries(self):
        from app.agents.map_analysis.mapping import judge_matches
        from app.llm.config import LLMSettings

        calls = []

        async def generate(prompt, raw):
            calls.append(raw)
            return (
                {"c1": {"status": "unclear", "reason": "자료 부족"}}
                if len(calls) < 3
                else {"c1": {"status": "same", "reason": "중식"}}
            )

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cache.sqlite3"
            for model in ("first", "first", "first", "second"):
                await judge_matches(
                    {
                        "c1": {
                            "target": {"code": "I212"},
                            "category": {"name": "중식", "code": "FD6"},
                        }
                    },
                    generate=generate,
                    settings=LLMSettings(model=model),
                    cache_path=path,
                )
        self.assertEqual(len(calls), 4)

    async def test_cached_categories_skip_model_and_only_send_unknown_categories(self):
        from app.agents.map_analysis.mapping import judge_matches
        from app.llm.config import LLMSettings

        calls = []

        async def generate(prompt, raw):
            categories = json.loads(raw)["pairs"]
            calls.append(categories)
            return {key: {"status": "same", "reason": "중식"} for key in categories}

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mapping.sqlite3"
            settings = LLMSettings(model="test")
            await judge_matches(
                {
                    "c1": {
                        "target": {"code": "I212"},
                        "category": {"name": "음식점 > 중식", "code": "FD6"},
                    }
                },
                generate=generate,
                settings=settings,
                cache_path=path,
            )
            result = await judge_matches(
                {
                    "c2": {
                        "target": {"code": "I212"},
                        "category": {"name": "음식점 > 중식", "code": "FD6"},
                    },
                    "c3": {
                        "target": {"code": "I212"},
                        "category": {"name": "새 분류", "code": "FD6"},
                    },
                },
                generate=generate,
                settings=settings,
                cache_path=path,
            )
            self.assertEqual(set(calls[1]), {"c3"})
            self.assertEqual(result["c2"].status, "same")

            async def failed(*args):
                raise RuntimeError("모델 실패")

            preserved = await judge_matches(
                {
                    "c4": {
                        "target": {"code": "I212"},
                        "category": {"name": "음식점 > 중식", "code": "FD6"},
                    },
                    "c5": {
                        "target": {"code": "I212"},
                        "category": {"name": "다른 미조회 분류", "code": "FD6"},
                    },
                },
                generate=failed,
                settings=settings,
                cache_path=path,
            )
            self.assertEqual(set(preserved), {"c4"})

    async def test_industry_search_uses_broad_category_without_changing_query(self):
        for code, query, category in (
            ("I212", "커피", "CE7"),
            ("I201", "백반", "FD6"),
            ("S209", "세탁", None),
            ("P105", "수학학원", "AC5"),
            ("P106", "미술학원", "AC5"),
            ("P107", "교육지원", None),
            ("Q101", "종합병원", "HP8"),
            ("Q102", "의원", "HP8"),
        ):

            def handle(req, query=query, category=category):
                self.assertEqual(req.url.params["query"], query)
                self.assertEqual(req.url.params.get("category_group_code"), category)
                return httpx.Response(
                    200, json={"meta": {"total_count": 0, "is_end": True}, "documents": []}
                )

            request = plan().model_copy(deep=True)
            request.queries[0].industry_code = code
            request.queries[0].query = query
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
                result = await agent.observe(
                    task(),
                    request,
                    client=PlaceClient(Settings(api_key="fake"), http),
                    generate_mapping=mapper,
                )
            self.assertEqual(result.data.queries["q1"].method, "keyword")

    async def test_malformed_place_does_not_discard_valid_sibling(self):
        data = payload()
        data["documents"].append(dict(data["documents"][0], id="broken", place_name=123))
        result = await self.observe(data)
        self.assertEqual(result.status, "partial")
        self.assertEqual(set(result.data.places), {"123"})
        self.assertEqual(result.data.industries["I212"].sampled_count, 1)

    async def test_empty_category_is_not_sent_to_mapper(self):
        data = payload()
        data["documents"][0]["category_name"] = ""
        data["documents"][0]["category_group_code"] = ""
        result = await self.observe(data)
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.data.queries["q1"].matches["123"], "unclear")
        self.assertEqual(result.data.industries, {})

    async def test_duplicate_raw_mapping_keys_are_rejected(self):
        from unittest.mock import AsyncMock, patch

        from openai.types.chat import ChatCompletionMessage

        from app.agents.map_analysis.mapping import judge_matches
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
            await judge_matches(
                {"c1": {"target": {"code": "I212"}, "category": {"name": "중식", "code": "FD6"}}},
                settings=LLMSettings(),
            )

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

    async def test_counts_same_matches_for_requested_industry_and_deduplicates(self):
        request = plan()
        request.queries.append(request.queries[0].model_copy(update={"query": "커피"}))
        result = await self.observe(payload(), request)
        self.assertEqual(len(result.data.places), 1)
        self.assertEqual(result.data.industries["I212"].sampled_count, 1)
        self.assertNotIn("I202", result.data.industries)
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
        self.assertEqual(result.data.queries["q1"].matches["123"], "unclear")
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
