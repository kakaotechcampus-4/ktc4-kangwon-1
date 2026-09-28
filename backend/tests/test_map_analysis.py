"""지도 조회 클라이언트가 외부 통신 없이 계약대로 도는지 검사함"""

from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import patch

import httpx

from app.agents.map_analysis.agent import search
from app.agents.map_analysis.client import MapApiError, PlaceClient
from app.agents.map_analysis.config import Settings
from app.agents.map_analysis.schemas import SearchResult
from app.schemas import Site

HIT: dict[str, Any] = {
    "meta": {"total_count": 100, "pageable_count": 45, "is_end": False},
    "documents": [
        {
            "place_name": "꼬꼬아찌숯불치킨 강남역점",
            "category_name": "음식점 > 치킨",
            "distance": "45",
            "x": "127.0276",
            "y": "37.4979",
            "place_url": "http://place.map.kakao.com/1",
        }
    ],
}
EMPTY: dict[str, Any] = {
    "meta": {"total_count": 0, "pageable_count": 0, "is_end": True},
    "documents": [],
}


def settings(**kwargs: Any) -> Settings:
    # 재시도 대기를 0으로 둬서 시험이 실제로 잠들지 않게 함
    return Settings(**{"api_key": "fake-key", "retry_backoff_s": 0.0, **kwargs})


class MapAnalysisClientTests(unittest.IsolatedAsyncioTestCase):
    async def call(
        self, handler: Any, *, config: Settings | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = PlaceClient(config or settings(), client=http)
            return await client.search_keyword("치킨", 37.4979, 127.0276, 500, **kwargs)

    @staticmethod
    def respond(status: int = 200, payload: Any = None) -> Any:
        return lambda request: httpx.Response(status, json=HIT if payload is None else payload)

    async def assert_code(self, code: str, handler: Any, **kwargs: Any) -> MapApiError:
        with self.assertRaises(MapApiError) as caught:
            await self.call(handler, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    # --- 요청 모양 ---

    async def test_request_carries_key_coordinates_and_radius(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v2/local/search/keyword.json")
            self.assertEqual(request.headers["Authorization"], "KakaoAK fake-key")
            params = request.url.params
            self.assertEqual(params["query"], "치킨")
            self.assertEqual(params["x"], "127.0276")
            self.assertEqual(params["y"], "37.4979")
            self.assertEqual(params["radius"], "500")
            self.assertEqual(params["sort"], "distance")
            self.assertEqual(params["size"], "15")
            # 분류 필터 안 주면 안 붙임
            self.assertNotIn("category_group_code", params)
            return httpx.Response(200, json=HIT)

        payload = await self.call(handler)
        self.assertEqual(payload["meta"]["total_count"], 100)

    async def test_category_filter_is_sent_when_given(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.params["category_group_code"], "FD6")
            return httpx.Response(200, json=HIT)

        await self.call(handler, category_group_code="FD6")

    async def test_category_search_uses_its_own_endpoint(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v2/local/search/category.json")
            self.assertEqual(request.url.params["category_group_code"], "SW8")
            self.assertNotIn("query", request.url.params)
            return httpx.Response(200, json=HIT)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = PlaceClient(settings(), client=http)
            await client.search_category("SW8", 37.4979, 127.0276, 500)

    async def test_empty_result_is_returned_not_an_error(self):
        payload = await self.call(self.respond(payload=EMPTY))
        self.assertEqual(payload["meta"]["total_count"], 0)
        self.assertEqual(payload["documents"], [])

    # --- 실패 구분 ---

    async def test_auth_failure_is_distinct_and_not_retried(self):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(401, json={"errorType": "x"})

        await self.assert_code("KAKAO_AUTH", handler)
        # 키 거부는 다시 물어도 같은 답이라 한 번만 부름
        self.assertEqual(len(calls), 1)
        await self.assert_code("KAKAO_AUTH", self.respond(403))

    async def test_timeout_and_broken_json_are_distinct(self):
        def timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timeout", request=request)

        await self.assert_code("UPSTREAM_TIMEOUT", timeout)
        await self.assert_code(
            "BAD_RESPONSE", lambda request: httpx.Response(200, content=b"not json")
        )

    async def test_broken_response_shape_is_rejected(self):
        for payload in (
            [],
            {"documents": []},
            {"meta": {}, "documents": []},
            {"meta": {"total_count": "100"}, "documents": []},
            {"meta": {"total_count": -1}, "documents": []},
            {"meta": {"total_count": 1}, "documents": {}},
        ):
            with self.subTest(payload=payload):
                await self.assert_code("BAD_RESPONSE", self.respond(payload=payload))

    async def test_client_error_other_than_auth_is_upstream_failed(self):
        await self.assert_code("UPSTREAM_FAILED", self.respond(400))

    # --- 재시도 ---

    async def test_retries_on_429_then_succeeds(self):
        attempts: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(1)
            if len(attempts) < 3:
                return httpx.Response(429, headers={"Retry-After": "0"})
            return httpx.Response(200, json=HIT)

        payload = await self.call(handler)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(payload["meta"]["total_count"], 100)

    async def test_gives_up_after_max_retries(self):
        attempts: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(1)
            return httpx.Response(503)

        await self.assert_code("UPSTREAM_FAILED", handler)
        # 최초 1회 + 재시도 2회
        self.assertEqual(len(attempts), 3)

    async def test_repeated_timeout_reports_timeout_not_failure(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timeout", request=request)

        await self.assert_code("UPSTREAM_TIMEOUT", handler)

    # --- 설정 검증은 네트워크 전에 ---

    async def test_bad_settings_and_input_never_connect(self):
        with patch("httpx.AsyncClient.send", side_effect=AssertionError("외부 연결 금지")):
            for code, config, kwargs in (
                ("CONFIG_ERROR", settings(api_key=None), {}),
                ("CONFIG_ERROR", settings(api_key="  "), {}),
                ("INVALID_RADIUS", settings(), {"radius_m": 0}),
                ("INVALID_RADIUS", settings(), {"radius_m": -1}),
                ("INVALID_RADIUS", settings(), {"radius_m": 20_001}),
                ("EMPTY_QUERY", settings(), {"query": "   "}),
            ):
                with self.subTest(code=code):
                    client = PlaceClient(config)
                    call = {"query": "치킨", "radius_m": 500, **kwargs}
                    with self.assertRaises(MapApiError) as caught:
                        await client.search_keyword(
                            call["query"], 37.4979, 127.0276, call["radius_m"]
                        )
                    self.assertEqual(caught.exception.code, code)

    # --- 키 누출 ---

    async def test_error_never_carries_the_key_or_upstream_body(self):
        secret = "SUPER-SECRET-KAKAO-KEY"
        config = settings(api_key=secret)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text=f"failed for {secret}")

        with self.assertRaises(MapApiError) as caught:
            await self.call(handler, config=config)
        rendered = f"{caught.exception} {caught.exception.message} {caught.exception.code}"
        self.assertNotIn(secret, rendered)

    async def test_settings_repr_hides_the_key(self):
        self.assertNotIn("fake-key", repr(settings()))

    # --- 수명 관리 ---

    async def test_injected_client_is_not_closed(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(self.respond())) as http:
            client = PlaceClient(settings(), client=http)
            await client.search_keyword("치킨", 37.4979, 127.0276, 500)
            await client.aclose()
            self.assertFalse(http.is_closed)

    async def test_environment_is_read_without_loading_dotenv(self):
        with patch.dict(os.environ, {"GEOCODING_API_KEY": "injected"}, clear=True):
            config = Settings.from_env()
        self.assertEqual(config.api_key, "injected")
        self.assertNotIn("injected", repr(config))


GANGNAM = Site(
    input_address="서울 강남구 테헤란로 152",
    road_address="서울 강남구 테헤란로 152",
    latitude=37.50035,
    longitude=127.03656,
)


def page(total: int, documents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "meta": {"total_count": total, "pageable_count": min(total, 45), "is_end": True},
        "documents": documents or [],
    }


def place(name: str, category: str, distance: str) -> dict[str, Any]:
    return {"place_name": name, "category_name": category, "distance": distance}


class MapAnalysisSearchTests(unittest.IsolatedAsyncioTestCase):
    async def run_search(self, handler: Any, queries: list[str], **kwargs: Any) -> SearchResult:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = PlaceClient(settings(), client=http)
            return await search(GANGNAM, queries, client=client, **kwargs)

    async def test_each_query_becomes_one_request_and_one_result(self):
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.params.get("query") or "")
            return httpx.Response(200, json=page(10))

        result = await self.run_search(handler, ["치킨", "한식", "피자"])
        self.assertEqual(seen, ["치킨", "한식", "피자"])
        self.assertEqual(list(result.results), ["치킨", "한식", "피자"])
        # 공통 계약을 한 번 더 통과시켜 둔다
        SearchResult.model_validate(result.model_dump())

    async def test_duplicate_queries_are_asked_once(self):
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(200, json=page(3))

        result = await self.run_search(handler, ["치킨", " 치킨 ", "치킨"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(list(result.results), ["치킨"])

    async def test_category_words_use_the_category_endpoint(self):
        paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            self.assertNotEqual(request.url.params.get("category_group_code"), None)
            return httpx.Response(200, json=page(2))

        # 키워드로 물으면 지하철역 14 vs 카테고리 2 로 부풀어서 분류 경로를 써야 한다
        await self.run_search(handler, ["지하철역", "유치원"])
        self.assertEqual(paths, ["/v2/local/search/category.json"] * 2)

    async def test_plain_words_use_the_keyword_endpoint(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v2/local/search/keyword.json")
            return httpx.Response(200, json=page(100))

        await self.run_search(handler, ["치킨"])

    async def test_count_nearest_and_brands_are_extracted(self):
        documents = [
            place("스타벅스 강남점", "음식점 > 카페 > 커피전문점 > 스타벅스", "12"),
            place("농민백암순대 강남직영점", "음식점 > 한식 > 순대", "30"),
            place("스타벅스 역삼점", "음식점 > 카페 > 커피전문점 > 스타벅스", "44"),
        ]
        result = await self.run_search(
            lambda request: httpx.Response(200, json=page(216, documents)), ["커피"]
        )
        found = result.results["커피"]
        self.assertEqual(found.count, 216)
        # 표본 3건 중 분류에 "커피"가 든 것은 둘
        self.assertEqual((found.sampled, found.matched), (3, 2))
        self.assertIsNotNone(found.nearest)
        assert found.nearest is not None
        self.assertEqual(found.nearest.name, "스타벅스 강남점")
        # 문자열 "12" 가 정수로 바뀌어야 한다
        self.assertEqual(found.nearest.distance_m, 12)
        # 순대는 브랜드가 아니므로 빠진다
        self.assertEqual(found.brands, {"스타벅스": 2})

    async def test_zero_result_has_no_nearest(self):
        result = await self.run_search(
            lambda request: httpx.Response(200, json=page(0)), ["말고기"]
        )
        found = result.results["말고기"]
        self.assertEqual(found.count, 0)
        self.assertIsNone(found.nearest)
        self.assertEqual(found.brands, {})
        # null 대신 키 자체가 빠져야 한다
        self.assertNotIn("nearest", found.model_dump(exclude_none=True))

    async def test_one_failing_query_does_not_kill_the_others(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.params.get("query") == "한식":
                return httpx.Response(500)
            return httpx.Response(200, json=page(7))

        result = await self.run_search(handler, ["치킨", "한식", "피자"])
        self.assertEqual(result.results["치킨"].count, 7)
        self.assertEqual(result.results["피자"].count, 7)
        self.assertEqual(result.results["한식"].error, "UPSTREAM_FAILED")
        self.assertEqual(result.results["한식"].count, 0)

    async def test_radius_is_passed_through_and_recorded(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.params["radius"], "300")
            return httpx.Response(200, json=page(1))

        result = await self.run_search(handler, ["치킨"], radius_m=300)
        self.assertEqual(result.radius_m, 300)

    async def test_school_words_never_leak_into_keyword_search(self):
        # "초등학교"를 키워드로 보내면 반경에 학교가 없는데도 도시락집이 1건 잡혔다.
        # 교육환경보호구역 판단에 그대로 쓰이면 거짓말이 되므로 분류 경로로 가야 한다.
        seen: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v2/local/search/category.json")
            seen.append(request.url.params.get("category_group_code"))
            return httpx.Response(200, json=page(0))

        result = await self.run_search(handler, ["초등학교", "중학교", "대학교"])
        self.assertEqual(seen, ["SC4", "SC4", "SC4"])
        self.assertEqual(result.results["초등학교"].count, 0)

    async def test_keyword_mismatch_is_reported_and_nearest_is_filtered(self):
        # 역삼에서 "치킨" 68곳이 나왔는데 최근접이 샌드위치집이었다.
        # count 는 못 고치니 표본 일치 건수를 같이 내고, 최근접은 일치한 것에서만 고른다.
        documents = [
            place("렌위치 역삼GFC점", "음식점 > 패스트푸드 > 샌드위치", "36"),
            place("아그라 역삼GFC점", "음식점 > 아시아음식 > 인도음식", "37"),
            place("치킨공식", "음식점 > 치킨", "169"),
        ]
        result = await self.run_search(
            lambda request: httpx.Response(200, json=page(68, documents)), ["치킨"]
        )
        found = result.results["치킨"]
        self.assertEqual(found.count, 68)
        self.assertEqual((found.sampled, found.matched), (3, 1))
        assert found.nearest is not None
        self.assertEqual(found.nearest.name, "치킨공식")

    async def test_category_search_counts_every_sample_as_matched(self):
        # 분류 조회는 카카오가 이미 걸러 준 결과라 검색어가 이름에 없어도 전부 맞다고 본다
        documents = [place("역삼역 2호선", "교통,수송 > 지하철,전철 > 수도권2호선", "36")]
        result = await self.run_search(
            lambda request: httpx.Response(200, json=page(1, documents)), ["지하철역"]
        )
        found = result.results["지하철역"]
        self.assertEqual((found.sampled, found.matched), (1, 1))
        assert found.nearest is not None
        self.assertEqual(found.nearest.name, "역삼역 2호선")

    async def test_empty_query_list_is_rejected(self):
        with patch("httpx.AsyncClient.send", side_effect=AssertionError("외부 연결 금지")):
            for queries in ([], ["", "   "]):
                with self.subTest(queries=queries):
                    with self.assertRaises(ValueError):
                        await search(GANGNAM, queries, settings=settings())


if __name__ == "__main__":
    unittest.main()
