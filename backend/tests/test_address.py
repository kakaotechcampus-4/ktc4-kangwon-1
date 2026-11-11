"""공통 주소 도구의 확정 정책을 외부 통신 없이 검증합니다."""

import copy
import os
import unittest
from unittest.mock import patch

import httpx

from app.infrastructure import config
from app.infrastructure.clients import address

ROAD = "서울 송파구 위례광장로 120"
HIT = {
    "meta": {"total_count": 1, "pageable_count": 1, "is_end": True},
    "documents": [
        {
            "x": "127.14164",
            "y": "37.47475",
            "road_address": {"address_name": ROAD},
            "address": {"address_name": "서울 송파구 장지동 887", "b_code": "1171011400"},
        }
    ],
}


def located(road, jibun=None, b_code=None, region=None):
    payload = copy.deepcopy(HIT)
    payload["documents"][0]["road_address"] = {
        "address_name": road,
        **({"region_1depth_name": region} if region else {}),
    }
    payload["documents"][0]["address"] = (
        {"address_name": jibun, **({"b_code": b_code} if b_code else {})} if jibun else None
    )
    return payload


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

    async def test_outside_seoul_is_refused(self):
        text = "부산 해운대구 해운대로 264"
        payload = located(text, "부산 해운대구 우동 1411", "2635010500")
        with self.assertRaises(address.GeocodeError) as caught:
            await self.resolve(text, payload=payload)
        self.assertEqual(caught.exception.code, "OUTSIDE_SEOUL")
        self.assertEqual(caught.exception.message, "지금은 서울 상가만 분석할 수 있어요.")

    async def test_gyeonggi_next_to_seoul_is_refused(self):
        for text, jibun, b_code in (
            ("경기 성남시 분당구 정자일로 95", "경기 성남시 분당구 정자동 178-1", "4113510900"),
            ("인천 부평구 부평대로 1", "인천 부평구 부평동 1", "2823710100"),
        ):
            with self.subTest(text=text):
                await self.assert_error(
                    "OUTSIDE_SEOUL", text=text, payload=located(text, jibun, b_code)
                )

    async def test_road_only_seoul_document_passes(self):
        site = await self.resolve(payload=located(ROAD, region="서울"))
        self.assertEqual((site.road_address, site.jibun_address), (ROAD, None))

    async def test_seoul_si_prefix_is_accepted(self):
        road = "서울 송파구 위례광장로 199"
        site = await self.resolve(
            "서울시 송파구 위례광장로 199",
            payload=located(road, "서울 송파구 장지동 893", "1171011400"),
        )
        self.assertEqual(site.road_address, road)

    def test_in_seoul_rules(self):
        for document, expected in (
            ({"address": {"b_code": "1171011400"}}, True),
            ({"address": {"b_code": "4113510900"}}, False),
            (
                {
                    "address": {"b_code": "4113510900"},
                    "road_address": {"region_1depth_name": "서울"},
                },
                False,
            ),
            ({"address": {}, "road_address": {"region_1depth_name": "서울특별시"}}, True),
            ({"address": None, "road_address": {"region_1depth_name": "서울"}}, True),
            ({"road_address": {"region_1depth_name": "경기"}}, False),
            ({"address": None, "road_address": None}, False),
        ):
            with self.subTest(document=document):
                self.assertIs(address.in_seoul(document), expected)

    async def test_incomplete_or_keyword_address_is_ambiguous(self):
        for text in ("개롱역", "서울 송파구", "서울 강남구 역삼1동", "위례광장로 120"):
            with self.subTest(text=text):
                await self.assert_error("ADDRESS_AMBIGUOUS", text=text)

    async def test_address_length_boundary_before_any_external_call(self):
        valid = ROAD + " " + "가" * (address.MAX_ADDRESS_LENGTH - len(ROAD) - 1)
        site = await self.resolve(valid)
        self.assertEqual(len(site.input_address), address.MAX_ADDRESS_LENGTH)
        with patch("httpx.AsyncClient.send", side_effect=AssertionError("긴 주소 조회 금지")):
            with self.assertRaises(address.GeocodeError) as caught:
                await address.resolve_site(valid + "가", self.settings())
        self.assertEqual(caught.exception.code, "ADDRESS_TOO_LONG")

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


if __name__ == "__main__":
    unittest.main()
