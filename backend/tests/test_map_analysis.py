"""지도 조회 클라이언트가 외부 통신 없이 계약대로 도는지 검사함"""

from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import patch

import httpx

from app.agents.map_analysis.agent import category_code, observe
from app.agents.map_analysis.client import MapApiError, PlaceClient
from app.agents.map_analysis.config import Settings
from app.schemas import AnalysisTask, MapLookupPlan, MapObservation, Site

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


class MapAnalysisObserveTests(unittest.IsolatedAsyncioTestCase):
    async def test_facilities_aliases_duplicates_radius_and_partial_failure(self):
        paths = []

        def handler(request):
            paths.append(request.url.path)
            self.assertEqual(request.url.params["radius"], "300")
            code = request.url.params["category_group_code"]
            if code == "SC4":
                return httpx.Response(401)
            return httpx.Response(200, json=page(0))

        queries = [
            dict(
                kind="infrastructure",
                facility_code=category_code(name),
                why_needed="접근성 확인",
                expected_impact="후보 비교",
            )
            for name in ["지하철역", "지하철", "초등학교"]
        ]
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            result = await observe(
                AnalysisTask(request_id="map-test", site=GANGNAM, radius_m=300),
                MapLookupPlan(action="map_lookup", queries=queries),
                client=PlaceClient(settings(), client=http),
            )
        MapObservation.model_validate(result.model_dump())
        self.assertEqual(paths, ["/v2/local/search/category.json"] * 2)
        self.assertEqual(result.radius_m, 300)
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.data.queries["q1"].total_count, 0)
        self.assertEqual(result.data.queries["q2"].error, "KAKAO_AUTH")


if __name__ == "__main__":
    unittest.main()
