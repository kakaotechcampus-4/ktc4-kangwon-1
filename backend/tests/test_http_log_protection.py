"""허브 호출 없이 앱 생성 직후 모든 httpx URL 로그를 보호합니다."""

import logging
import unittest
from unittest.mock import patch

import httpx

from app.main import create_app


class HttpLogProtectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_app_creation_protects_all_service_urls_without_hub_lookup(self):
        urls = [
            "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo?serviceKey=hub-fake",
            "https://dapi.kakao.com/v2/local/search/address.json?key=kakao-fake&query=test",
            "http://openapi.seoul.go.kr:8088/seoul-fake/json/Test/1/1",
            "https://api.vworld.kr/req/data?key=vworld-fake&request=GetFeature",
            "https://dapi.kakao.com/v2/local/search/category.json?key=map-fake&category_group_code=BK9",
        ]
        logger = logging.getLogger("httpx")
        with patch.object(logger, "filters", []):
            create_app(load_env=False)
            create_app(load_env=False)
            filter_count = len(logger.filters)
            with self.assertLogs("httpx", level=logging.INFO) as captured:
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
                ) as client:
                    for url in urls:
                        await client.get(url, headers={"Authorization": "KakaoAK header-fake"})
        output = "\n".join(captured.output)
        self.assertEqual(len(captured.output), 5)
        for secret in (
            "hub-fake",
            "kakao-fake",
            "seoul-fake",
            "vworld-fake",
            "map-fake",
            "header-fake",
        ):
            self.assertNotIn(secret, output)
        for endpoint in (
            "getBrTitleInfo",
            "address.json",
            "/json/Test/1/1",
            "GetFeature",
            "category.json",
        ):
            self.assertIn(endpoint, output)
        self.assertEqual(filter_count, 1)


if __name__ == "__main__":
    unittest.main()
