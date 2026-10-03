"""동일 서버 루프의 서로 다른 분석도 조회 슬롯을 공유합니다."""

import asyncio
import unittest

import httpx

from app.agents.commercial_area.client import StoreClient
from app.agents.commercial_area.config import Settings


class ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_pagination_does_not_queue_all_pages_ahead_of_other_user(self):
        entered, release = asyncio.Event(), asyncio.Event()
        order = []

        async def respond(request):
            user = request.url.params["key"]
            page = int(request.url.params["pageNo"])
            order.append((user, page))
            if user == "large" and page == 2:
                entered.set()
                await release.wait()
            return httpx.Response(
                200,
                json={
                    "body": {"items": [{"page": page}], "totalCount": 120 if user == "large" else 1}
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            settings = Settings(sbiz_service_key="test", page_size=1, max_concurrency=1)
            large, small = StoreClient(settings, http), StoreClient(settings, http)
            running = asyncio.create_task(
                large._collect_pages(lambda p: large._request_district_page("large", p), 120)
            )
            await asyncio.wait_for(entered.wait(), 1)
            # 이미 실행 중인 첫 사용자 뒤에 두 번째 사용자의 조회를 등록합니다.
            other = asyncio.create_task(small._request_district_page("small", 1))
            await asyncio.sleep(0)
            release.set()
            rows, total = await asyncio.wait_for(running, 3)
            await other
        self.assertEqual(total, 120)
        self.assertEqual([row["page"] for row in rows], list(range(1, 121)))
        self.assertLess(order.index(("small", 1)), 5)

    async def test_multiple_clients_share_limit_and_release_after_failure(self):
        active = peak = 0

        async def respond(request):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.01)
                if request.url.params["pageNo"] == "1":
                    raise httpx.ReadTimeout("시험")
                return httpx.Response(200, json={"body": {"items": [], "totalCount": 0}})
            finally:
                active -= 1

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            settings = Settings(sbiz_service_key="시험", max_concurrency=2, max_retries=0)
            clients = [StoreClient(settings, http) for _ in range(2)]
            results = await asyncio.gather(
                *(
                    client._request_page(37.5, 127, 300, page)
                    for client in clients
                    for page in range(1, 5)
                ),
                return_exceptions=True,
            )
            self.assertEqual(sum(isinstance(result, Exception) for result in results), 2)
            await asyncio.wait_for(clients[0]._request_page(37.5, 127, 300, 2), 1)
        self.assertLessEqual(peak, 2)
