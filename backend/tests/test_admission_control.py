"""응답 대기 방식과 무관한 분석 접수 제한을 검사합니다."""

import asyncio
import unittest

import httpx
from fastapi import Response

from app.api.v1.routes import analysis_runner
from app.main import create_app
from app.services.settings import ExecutionSettings


class AdmissionControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_wait_true_and_false_share_capacity(self):
        app = create_app(settings=ExecutionSettings(max_concurrency=2), load_env=False)
        started: asyncio.Queue = asyncio.Queue()
        release = asyncio.Event()

        async def execute(*args, **kwargs):
            await started.put(kwargs["request_id"])
            await release.wait()
            return Response(content="{}", media_type="application/json")

        app.dependency_overrides[analysis_runner] = lambda: execute
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            waiting = asyncio.create_task(
                client.post("/api/v1/analyses?mock=true", json={"address": "시험 주소"})
            )
            try:
                await asyncio.wait_for(started.get(), timeout=2)
                background = await client.post(
                    "/api/v1/analyses?mock=true&wait=false", json={"address": "시험 주소"}
                )
                self.assertEqual(background.status_code, 202)
                await asyncio.wait_for(started.get(), timeout=2)
                rejected = await asyncio.wait_for(
                    client.post("/api/v1/analyses?mock=true", json={"address": "시험 주소"}),
                    timeout=2,
                )
                self.assertEqual(rejected.status_code, 429)
                self.assertEqual(rejected.headers["retry-after"], "30")
                self.assertIn("x-request-id", rejected.headers)
                self.assertEqual(
                    rejected.json()["detail"],
                    "동시에 실행할 수 있는 분석 수를 넘었습니다. 잠시 뒤 다시 요청해 주세요.",
                )
            finally:
                release.set()
                await waiting
                await app.state.job_registry.shutdown()

    async def test_wait_true_failure_releases_capacity(self):
        app = create_app(settings=ExecutionSettings(max_concurrency=1), load_env=False)

        async def execute(*args, **kwargs):
            raise RuntimeError("대역 실패")

        app.dependency_overrides[analysis_runner] = lambda: execute
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(2):
                response = await client.post(
                    "/api/v1/analyses?mock=true", json={"address": "시험 주소"}
                )
                self.assertEqual(response.status_code, 502)
                self.assertFalse(app.state.job_registry.tasks)
