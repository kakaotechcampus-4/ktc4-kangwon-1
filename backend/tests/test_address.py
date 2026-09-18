"""공통 주소 도구의 확정 정책을 외부 통신 없이 검증합니다."""

import copy
import os
import unittest
from functools import partial
from unittest.mock import patch

import httpx

from app import address, config
from app.agents.commercial_area.config import Settings
from app.agents.orchestration.workflow import prepare_task, run_agents, run_analysis
from app.mocks import mock_agents, mock_generate
from app.schemas import AgentAnalysis, Scope

ROAD = "서울 송파구 위례광장로 120"
HIT = {
    "meta": {"total_count": 1, "pageable_count": 1, "is_end": True},
    "documents": [
        {
            "x": "127.14164",
            "y": "37.47475",
            "road_address": {"address_name": ROAD},
            "address": {"address_name": "서울 송파구 장지동 887"},
        }
    ],
}


class AddressTests(unittest.IsolatedAsyncioTestCase):
    def settings(self, **kwargs):
        return config.AddressSettings(**{"api_key": "fake-key", **kwargs})

    async def resolve(self, text=ROAD, *, payload=None, status=200):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status, json=HIT if payload is None else payload)
            )
        ) as client:
            return await address.resolve_site(text, self.settings(), client=client)

    async def assert_error(self, code, **kwargs):
        with self.assertRaises(address.GeocodeError) as caught:
            await self.resolve(**kwargs)
        self.assertEqual(caught.exception.code, code)

    async def test_only_base_address_is_sent_and_original_detail_preserved(self):
        original = "  서울특별시  송파구 위례광장로 120, 큰빌딩 2층 201호  "

        def handler(request):
            self.assertEqual(request.url.path, "/v2/local/search/address.json")
            self.assertEqual(request.url.params["query"], "서울특별시  송파구 위례광장로 120")
            self.assertGreater(int(request.url.params["size"]), 1)
            self.assertEqual(request.headers["Authorization"], "KakaoAK fake-key")
            return httpx.Response(200, json=HIT)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            site = await address.resolve_site(original, self.settings(), client=client)
            self.assertFalse(client.is_closed)
        self.assertEqual(site.input_address, original.strip())
        self.assertEqual(site.detail_address, "큰빌딩 2층 201호")
        self.assertEqual((site.latitude, site.longitude), (37.47475, 127.14164))

    async def test_jibun_and_numbered_dong_names_are_not_details(self):
        for base in (
            "서울 송파구 장지동 887",
            "서울 강남구 역삼1동 123",
            "서울 성동구 성수동2가 123-4",
        ):
            with self.subTest(base=base):
                payload = copy.deepcopy(HIT)
                payload["documents"][0]["road_address"] = None
                payload["documents"][0]["address"]["address_name"] = base
                site = await self.resolve(base + " 101동 지하 1층", payload=payload)
                self.assertEqual(site.jibun_address, base)
                self.assertEqual(site.detail_address, "101동 지하 1층")

    async def test_region_and_number_mismatch_are_rejected(self):
        for text in ("부산 송파구 위례광장로 120", "서울 강남구 위례광장로 120", ROAD + "-1"):
            with self.subTest(text=text):
                await self.assert_error("ADDRESS_MISMATCH", text=text)

    async def test_incomplete_or_keyword_address_is_ambiguous(self):
        for text in ("개롱역", "서울 송파구", "서울 강남구 역삼1동", "위례광장로 120"):
            with self.subTest(text=text):
                await self.assert_error("ADDRESS_AMBIGUOUS", text=text)

    async def test_building_name_before_base_never_influences_search(self):
        with patch("httpx.AsyncClient.send", side_effect=AssertionError("잘못된 주소 조회 금지")):
            with self.assertRaises(address.GeocodeError) as caught:
                await address.resolve_site("서울 송파구 큰빌딩 위례광장로 120", self.settings())
        self.assertEqual(caught.exception.code, "ADDRESS_AMBIGUOUS")

    async def test_multiple_candidates_and_hidden_pages_are_ambiguous(self):
        for changes in ({"total_count": 2}, {"pageable_count": 2}, {"is_end": False}):
            payload = copy.deepcopy(HIT)
            payload["meta"].update(changes)
            with self.subTest(changes=changes):
                await self.assert_error("ADDRESS_AMBIGUOUS", payload=payload)
        payload = copy.deepcopy(HIT)
        payload["documents"] *= 2
        await self.assert_error("ADDRESS_AMBIGUOUS", payload=payload)

    async def test_empty_result_is_not_found(self):
        await self.assert_error(
            "NOT_FOUND",
            payload={
                "meta": {"total_count": 0, "pageable_count": 0, "is_end": True},
                "documents": [],
            },
        )

    async def test_broken_response_contract_is_rejected(self):
        for payload in (
            [],
            {},
            {"meta": HIT["meta"], "documents": "broken"},
            {"meta": {**HIT["meta"], "total_count": "1"}, "documents": HIT["documents"]},
        ):
            with self.subTest(payload=payload):
                await self.assert_error("BAD_RESPONSE", payload=payload)
        for change in (
            {"road_address": None, "address": None},
            {"road_address": "broken"},
            {"road_address": {"address_name": 123}},
            {"x": "NaN"},
            {"y": "inf"},
            {"y": 91},
            {"x": 181},
            {"x": True},
            {"x": None},
        ):
            payload = copy.deepcopy(HIT)
            payload["documents"][0].update(change)
            with self.subTest(change=change):
                await self.assert_error("BAD_RESPONSE", payload=payload)

    async def test_auth_and_other_http_errors_are_distinct(self):
        for status in (401, 403):
            await self.assert_error("KAKAO_AUTH", status=status)
        await self.assert_error("UPSTREAM_FAILED", status=500)

    async def test_invalid_json_and_timeout_are_distinct(self):
        for code in ("BAD_RESPONSE", "UPSTREAM_TIMEOUT"):

            def handler(request, code=code):
                if code == "UPSTREAM_TIMEOUT":
                    raise httpx.ReadTimeout("timeout", request=request)
                return httpx.Response(200, content=b"not JSON")

            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(address.GeocodeError) as caught:
                    await address.resolve_site(ROAD, self.settings(), client=client)
                self.assertEqual(caught.exception.code, code)

    async def test_missing_key_and_invalid_timeout_never_connect(self):
        with patch("httpx.AsyncClient.send", side_effect=AssertionError("외부 연결 금지")):
            for kwargs in (
                {"api_key": None},
                {"api_key": " "},
                {"api_key": 123},
                {"timeout": 0},
                {"timeout": "bad"},
                {"timeout": float("nan")},
            ):
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises(address.GeocodeError) as caught:
                        await address.resolve_site(ROAD, self.settings(**kwargs))
                    self.assertEqual(caught.exception.code, "ADDRESS_CONFIG_ERROR")

    async def test_mock_zero_coordinates_cannot_be_confirmed_by_provider(self):
        payload = copy.deepcopy(HIT)
        payload["documents"][0].update(x="0", y="0")
        await self.assert_error("BAD_RESPONSE", payload=payload)

    async def test_empty_address_is_rejected(self):
        await self.assert_error("EMPTY_ADDRESS", text="  ")

    async def test_environment_is_read_without_loading_dotenv(self):
        self.settings()
        with (
            patch.dict(os.environ, {"GEOCODING_API_KEY": "injected"}, clear=True),
            patch.object(config, "load_dotenv", side_effect=AssertionError("환경 파일 읽기 금지")),
        ):
            settings = config.AddressSettings.from_env()
        self.assertEqual(settings.api_key, "injected")
        self.assertNotIn("injected", repr(settings))

    async def test_prepare_resolves_once_and_analysts_reuse_site(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=HIT)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            task = await prepare_task(
                ROAD, resolve=partial(address.resolve_site, settings=self.settings(), client=client)
            )
            seen = []

            async def analyze(task):
                seen.append(task.site)
                return AgentAnalysis(
                    request_id=task.request_id,
                    agent_id="commercial_area",
                    status="no_data",
                    scope=Scope(area=ROAD, period="시험"),
                )

            await run_agents(task, {"commercial_area": analyze})
        self.assertEqual(len(requests), 1)
        self.assertIs(seen[0], task.site)

    async def test_legacy_workflow_settings_forward_key_and_timeout(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=HIT)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:

            async def resolve(text, settings):
                return await address.resolve_site(text, settings, client=client)

            with patch("app.agents.orchestration.tools.resolve_site", side_effect=resolve):
                result = await run_analysis(
                    ROAD,
                    settings=Settings(geocoding_api_key="legacy", request_timeout_s=7),
                    agents=mock_agents(),
                    generate=mock_generate,
                )
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].headers["Authorization"], "KakaoAK legacy")
        self.assertEqual(requests[0].extensions["timeout"]["read"], 7)


if __name__ == "__main__":
    unittest.main()
