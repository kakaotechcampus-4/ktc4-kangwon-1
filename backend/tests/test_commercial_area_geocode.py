"""주소를 좌표로 바꾸는 과정을 검사합니다."""

import unittest
from unittest.mock import patch

import httpx

from app.agents.commercial_area.config import Settings
from app.agents.commercial_area.geocode import GeocodeError, geocode

KAKAO_HIT = {
    "documents": [
        {
            "x": "127.14164",
            "y": "37.47475",
            "road_address": {"address_name": "서울 송파구 위례광장로 120"},
            "address": {"address_name": "서울 송파구 장지동 887"},
        }
    ]
}
NOMINATIM_HIT = [
    {"lat": "37.47475", "lon": "127.14164", "display_name": "120, 위례광장로, 송파구, 서울특별시"}
]


class GeocodeTests(unittest.IsolatedAsyncioTestCase):
    def _patched(self, handler):
        original = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs.pop("timeout", None)
            return original(transport=httpx.MockTransport(handler), **kwargs)

        return patch.object(httpx, "AsyncClient", factory)

    async def test_uses_geocoding_key_when_present(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json=KAKAO_HIT)

        with self._patched(handler):
            result = await geocode(
                "서울특별시 송파구 위례광장로 120 155호", Settings(geocoding_api_key="test-key")
            )

        self.assertEqual(result.provider, "kakao")
        self.assertEqual(result.detail_address, "155호")
        self.assertEqual(round(result.latitude, 5), 37.47475)
        self.assertEqual(seen["auth"], "KakaoAK test-key")

    async def test_falls_back_to_open_map_without_key(self):
        with self._patched(lambda request: httpx.Response(200, json=NOMINATIM_HIT)):
            result = await geocode("서울특별시 송파구 위례광장로 120", Settings())
        self.assertEqual(result.provider, "nominatim")
        self.assertEqual(result.confidence, "low")

    async def test_not_found_is_reported(self):
        with self._patched(lambda request: httpx.Response(200, json=[])):
            with self.assertRaises(GeocodeError) as ctx:
                await geocode("없는주소", Settings())
        self.assertEqual(ctx.exception.code, "NOT_FOUND")

    async def test_rejected_key_is_reported(self):
        with self._patched(lambda request: httpx.Response(401, json={})):
            with self.assertRaises(GeocodeError) as ctx:
                await geocode("서울특별시 송파구 위례광장로 120", Settings(geocoding_api_key="bad"))
        self.assertEqual(ctx.exception.code, "KAKAO_AUTH")

    async def test_empty_address_rejected(self):
        with self.assertRaises(GeocodeError) as ctx:
            await geocode("   ", Settings())
        self.assertEqual(ctx.exception.code, "EMPTY_ADDRESS")


if __name__ == "__main__":
    unittest.main()
