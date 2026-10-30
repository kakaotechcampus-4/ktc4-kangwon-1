"""허브의 키 보호·오류 분류·조회 상한·주소 검증을 대역으로 확인합니다."""

import logging
import traceback
import unittest

import httpx
import test_building_registry as fixtures
from test_building_registry import answers, hub

from app.address import GeocodeError
from app.building_registry import BuildingRegistryError


class BuildingSafetyTests(unittest.IsolatedAsyncioTestCase):
    lookup = fixtures.BuildingRegistryTests.lookup

    async def test_unit_page_limit_preserves_other_sections(self):
        pages = []

        def page(request):
            number = int(request.url.params["pageNo"])
            pages.append(number)
            rows = [{"hoNm": f"{number}-{i}", "exposPubuseGbCdNm": "전유"} for i in range(100)]
            return httpx.Response(200, json=hub(rows, total=3001))

        result, _ = await self.lookup(answers(getBrExposPubuseAreaInfo=page))
        self.assertEqual(pages, list(range(1, 31)))
        self.assertIsNone(result.units)
        self.assertEqual((len(result.titles), len(result.floors), len(result.sewage)), (1, 2, 1))

    async def test_rate_limit_and_auth_codes_are_distinct_without_retry(self):
        for response, code in (
            (httpx.Response(429), "RATE_LIMIT"),
            (httpx.Response(401), "AUTH"),
            (httpx.Response(403), "AUTH"),
            (
                httpx.Response(
                    200,
                    content=b"\xef\xbb\xbf<OpenAPI_ServiceResponse>"
                    b"<cmmMsgHeader><returnReasonCode>22</returnReasonCode>"
                    b"</cmmMsgHeader></OpenAPI_ServiceResponse>",
                ),
                "RATE_LIMIT",
            ),
            (httpx.Response(200, json={"response": {"header": {"resultCode": "30"}}}), "AUTH"),
            (
                httpx.Response(
                    200,
                    text="<OpenAPI_ServiceResponse><cmmMsgHeader>"
                    "<returnReasonCode>22</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>",
                ),
                "RATE_LIMIT",
            ),
            (
                httpx.Response(
                    200,
                    text="<OpenAPI_ServiceResponse><cmmMsgHeader>"
                    "<returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>",
                ),
                "AUTH",
            ),
        ):
            with self.subTest(code=code, status=response.status_code):
                counts = []

                def failed(request, counts=counts, response=response):
                    counts.append(request)
                    return response

                with self.assertRaises(BuildingRegistryError) as caught:
                    await self.lookup({name: failed for name in answers()})
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(len(counts), 4)

    async def test_httpx_info_does_not_expose_query_key(self):
        from app.main import create_app

        create_app(load_env=False)
        with self.assertLogs("httpx", level=logging.INFO) as captured:
            await self.lookup(answers(), key="dummy/secret+with=encoding")
        logs = "\n".join(captured.output)
        self.assertNotIn("serviceKey", logs)
        self.assertNotIn("dummy", logs)
        self.assertIn("getBrTitleInfo", logs)

    async def test_untrusted_result_code_is_not_in_error(self):
        response = httpx.Response(
            200, json={"response": {"header": {"resultCode": "private-body"}}}
        )
        with self.assertRaises(BuildingRegistryError) as caught:
            await self.lookup({name: response for name in answers()})
        self.assertEqual(caught.exception.code, "UPSTREAM_ERROR")
        self.assertNotIn("private-body", str(caught.exception))

    async def test_http_failure_traceback_does_not_expose_query_key(self):
        try:
            await self.lookup({name: httpx.Response(400) for name in answers()})
        except BuildingRegistryError:
            output = traceback.format_exc()
        else:
            self.fail("오류 응답을 성공으로 처리했습니다.")
        self.assertNotIn("serviceKey=fake", output)

    async def test_mismatched_address_stops_before_hub(self):
        from unittest.mock import patch

        with patch(
            "test_building_registry.KAKAO",
            {
                "meta": {"total_count": 1, "pageable_count": 1, "is_end": True},
                "documents": [
                    {
                        "address": {
                            "address_name": "서울 송파구 장지동 893",
                            "b_code": "1171011400",
                        },
                        "road_address": {"address_name": "서울 송파구 위례광장로 200"},
                    }
                ],
            },
        ):
            called = []

            def forbidden(request):
                called.append(request)
                return httpx.Response(200, json=hub([]))

            with self.assertRaises(GeocodeError) as caught:
                await self.lookup({name: forbidden for name in answers()})
            self.assertEqual(caught.exception.code, "ADDRESS_MISMATCH")
            self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
