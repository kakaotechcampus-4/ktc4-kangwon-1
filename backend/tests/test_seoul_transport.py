"""서울 API 전송과 최신 분기 재사용을 검사합니다."""

import asyncio
import unittest
from unittest.mock import patch

import httpx

from app.agents.business_lifecycle.client import request_page
from app.agents.floating_population.client import SeoulOpenDataClient
from app.agents.floating_population.config import Settings


class SeoulTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifecycle_quarters_are_bounded_parallel_and_keep_order(self):
        from app.agents.business_lifecycle.client import (
            fetch_store_data_for_quarters,
            get_recent_quarters,
        )

        active = peak = 0
        quarters = get_recent_quarters("20244", 12)

        async def fetch(*, quarter, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0)
                return [] if quarter == "20232" else [{"quarter": quarter}]
            finally:
                active -= 1

        with patch("app.agents.business_lifecycle.client.fetch_store_data", side_effect=fetch):
            rows = await fetch_store_data_for_quarters("test", quarters)
        self.assertGreater(peak, 1)
        self.assertLessEqual(peak, 4)
        self.assertEqual([r["quarter"] for r in rows], [q for q in quarters if q != "20232"])
        self.assertEqual(active, 0)

    async def test_failed_quarter_cancels_other_fetches_before_return(self):
        from app.agents.business_lifecycle.client import (
            SeoulOpenAPIError,
            fetch_store_data_for_quarters,
        )

        active = 0

        async def fetch(*, quarter, **kwargs):
            nonlocal active
            active += 1
            try:
                await asyncio.sleep(0)
                if quarter == "20241":
                    raise SeoulOpenAPIError("시험 실패")
                await asyncio.Event().wait()
            finally:
                active -= 1

        with patch("app.agents.business_lifecycle.client.fetch_store_data", side_effect=fetch):
            with self.assertRaises(SeoulOpenAPIError):
                await fetch_store_data_for_quarters("test", ["20241", "20242", "20243"])
        self.assertEqual(active, 0)

    async def test_lifecycle_probe_page_is_reused_only_inside_request(self):
        from app.agents.business_lifecycle.client import page_session

        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"VwsmTrdarStorQq": {"row": [], "list_total_count": 0}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            for _ in range(2):
                async with page_session(10, http=http):
                    first = await request_page("test", "20244", "3120240", 1, 1000)
                    first["VwsmTrdarStorQq"]["row"].append({"changed": True})
                    second = await request_page("test", "20244", "3120240", 1, 1000)
                    self.assertEqual(second["VwsmTrdarStorQq"]["row"], [])
        self.assertEqual(len(requests), 2)

    async def test_lifecycle_uses_injected_async_transport(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"VwsmTrdarStorQq": {"row": [], "list_total_count": 0}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            payload = await request_page("test", "20244", "3120240", 1, 1000, http=http)
        self.assertEqual(payload["VwsmTrdarStorQq"]["row"], [])
        self.assertEqual(requests[0].url.path, "/test/json/VwsmTrdarStorQq/1/1000/20244/3120240/")

    async def test_latest_quarter_is_reused_inside_one_client(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "VwsmTrdarFlpopQq": {
                        "RESULT": {"CODE": "INFO-000"},
                        "list_total_count": 1,
                        "row": [],
                    }
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            client = SeoulOpenDataClient(Settings(api_key="test"), http=http)
            first = await client.latest_quarter()
            self.assertEqual(await client.latest_quarter(), first)
        self.assertEqual(len(requests), 1)
