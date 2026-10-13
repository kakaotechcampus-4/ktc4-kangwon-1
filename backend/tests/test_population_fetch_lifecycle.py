"""서울 인구 빈 응답과 병렬 조회의 정리를 가짜 전송으로 검사합니다."""

import asyncio
import unittest
from datetime import date
from unittest.mock import patch

import httpx

from app.agents.floating_population.client import SeoulOpenApiError, SeoulOpenDataClient
from app.agents.floating_population.config import Settings


class PopulationFetchLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_top_level_no_data_is_an_empty_page(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"RESULT": {"CODE": "INFO-200"}})
        )
        async with httpx.AsyncClient(transport=transport) as http:
            client = SeoulOpenDataClient(Settings(api_key="test"), http=http)
            self.assertEqual(await client._fetch_all("service", 1), [])

    async def test_quarter_probe_skips_top_level_empty_response(self):
        calls = []

        def respond(request):
            calls.append(str(request.url))
            service = Settings().flpop_service
            return httpx.Response(
                200,
                json={"RESULT": {"CODE": "INFO-200"}}
                if len(calls) == 1
                else {service: {"RESULT": {"CODE": "INFO-000"}, "list_total_count": 1, "row": []}},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            client = SeoulOpenDataClient(
                Settings(api_key="test"), http=http, today=date(2026, 7, 1)
            )
            self.assertEqual(await client.latest_quarter(), "20262")
            self.assertEqual(len(calls), 2)

    async def test_failed_fetch_settles_other_tasks_before_client_close(self):
        started = asyncio.Event()
        order = []

        async def respond(request):
            if str(request.url).endswith("20261/"):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    order.append("sibling_settled")
            await started.wait()
            raise httpx.ConnectError("test failure", request=request)

        client = SeoulOpenDataClient(Settings(api_key="test"))
        client._latest_quarter = "20262"
        http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        original_close = http.aclose

        async def close():
            order.append("client_close")
            await original_close()

        with (
            patch.object(client, "http", return_value=http),
            patch.object(http, "aclose", side_effect=close),
        ):
            client._http = http
            async with client:
                with self.assertRaises(SeoulOpenApiError):
                    await client.fetch_flpop_series({"test"}, 2)
            self.assertEqual(order, ["sibling_settled", "client_close"])

    async def test_cancellation_settles_all_fetches(self):
        started = asyncio.Event()
        settled = []

        async def respond(request):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                settled.append(str(request.url))

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            client = SeoulOpenDataClient(Settings(api_key="test"), http=http)
            client._latest_quarter = "20262"
            task = asyncio.create_task(client.fetch_flpop_series({"test"}, 2))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(len(settled), 2)
