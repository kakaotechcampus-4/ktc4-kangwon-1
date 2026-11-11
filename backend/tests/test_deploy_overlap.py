import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.infrastructure.persistence.connection import initialize
from app.infrastructure.persistence.repository import requests
from app.infrastructure.settings import ExecutionSettings
from app.main import create_app


class DeployOverlapTests(unittest.IsolatedAsyncioTestCase):
    def status(self, request_id):
        return requests.get_request(request_id, db_path=self.path)["status"]

    def start_app(self, instance, *, drain):
        settings = ExecutionSettings(db_path=self.path, shutdown_drain_seconds=drain)
        with patch.dict(os.environ, {"CHAEUM_INSTANCE": instance}):
            return create_app(settings=settings, load_env=False)

    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = initialize(Path(directory.name) / "shared.sqlite3")

    async def run_overlap(self, *, drain, finish_during_drain):
        release = asyncio.Event()

        async def work():
            try:
                await release.wait()
            except asyncio.CancelledError:
                requests.record_failure(
                    "inflight",
                    error_text=json.dumps({"code": "INTERRUPTED", "message": "멈춤"}),
                    diagnostics_text="[]",
                    failed_at="2026-11-11T00:00:00+00:00",
                    db_path=self.path,
                )
                raise
            requests.save_outcome(
                "inflight",
                result_text=json.dumps({"request_id": "inflight"}),
                completed_at="2026-11-11T00:00:00+00:00",
                db_path=self.path,
            )

        old = self.start_app("8001", drain=drain)
        new = self.start_app("8002", drain=drain)
        with patch.dict(os.environ, {"CHAEUM_INSTANCE": "8001"}):
            async with old.router.lifespan_context(old):
                requests.create_request("inflight", "서울 송파구 오금로 404", db_path=self.path)
                requests.mark_running("inflight", db_path=self.path)
                old.state.job_registry.start("inflight", work())
                await asyncio.sleep(0)
                serving = new.router.lifespan_context(new)
                with patch.dict(os.environ, {"CHAEUM_INSTANCE": "8002"}):
                    await serving.__aenter__()
                self.addAsyncCleanup(serving.__aexit__, None, None, None)
                self.assertEqual(self.status("inflight"), "running")
                if finish_during_drain:
                    asyncio.get_running_loop().call_later(0.05, release.set)
        return self.status("inflight")

    async def test_old_server_finishes_running_analysis_after_new_server_starts(self):
        self.assertEqual(await self.run_overlap(drain=5, finish_during_drain=True), "completed")

    async def test_analysis_longer_than_drain_window_is_closed_as_interrupted(self):
        self.assertEqual(await self.run_overlap(drain=0.05, finish_during_drain=False), "failed")

    async def test_restart_of_same_server_still_closes_its_interrupted_analysis(self):
        with patch.dict(os.environ, {"CHAEUM_INSTANCE": "8001"}):
            requests.create_request("crashed", "서울 송파구 오금로 404", db_path=self.path)
            requests.mark_running("crashed", db_path=self.path)
            restarted = self.start_app("8001", drain=5)
            async with restarted.router.lifespan_context(restarted):
                self.assertEqual(self.status("crashed"), "failed")
