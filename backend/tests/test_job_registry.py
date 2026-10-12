"""분석 작업의 소유권과 취소 후 정리를 검사합니다."""

import asyncio
import inspect
import unittest

from app.services.jobs import AnalysisJobRegistry, JobClosedError, JobConflictError, JobLimitError


class JobRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_id_keeps_original_and_closes_rejected_work(self):
        registry = AnalysisJobRegistry(2)
        gate = asyncio.Event()
        original = registry.start("request", gate.wait())
        rejected = gate.wait()
        with self.assertRaises(JobConflictError):
            registry.start("request", rejected)
        self.assertEqual(inspect.getcoroutinestate(rejected), inspect.CORO_CLOSED)
        self.assertIs(registry.tasks["request"], original)
        gate.set()
        await original
        await asyncio.sleep(0)
        self.assertFalse(registry.is_active("request"))

    async def test_capacity_rejection_closes_work(self):
        registry = AnalysisJobRegistry(1)
        task = registry.start("first", asyncio.Event().wait())
        rejected = asyncio.Event().wait()
        with self.assertRaises(JobLimitError):
            registry.start("second", rejected)
        self.assertEqual(inspect.getcoroutinestate(rejected), inspect.CORO_CLOSED)
        await registry.shutdown()
        self.assertTrue(task.cancelled())

    async def test_shutdown_waits_for_cleanup_and_stops_accepting(self):
        registry = AnalysisJobRegistry(2)
        started, cleaned = asyncio.Event(), asyncio.Event()

        async def work():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        registry.start("first", work())
        await started.wait()
        await registry.shutdown()
        self.assertTrue(cleaned.is_set())
        rejected = asyncio.Event().wait()
        with self.assertRaises(JobClosedError):
            registry.start("second", rejected)
        self.assertEqual(inspect.getcoroutinestate(rejected), inspect.CORO_CLOSED)

    async def test_failure_releases_task_without_logging_original_error(self):
        registry = AnalysisJobRegistry(1)

        async def fail():
            raise RuntimeError("secret-sentinel")

        with self.assertLogs("app.services.jobs", level="WARNING") as logs:
            task = registry.start("request", fail())
            with self.assertRaises(RuntimeError):
                await task
            await asyncio.sleep(0)
        self.assertFalse(registry.is_active("request"))
        self.assertNotIn("secret-sentinel", "\n".join(logs.output))

    async def test_shutdown_deadline_does_not_cancel_cleanup_twice(self):
        registry = AnalysisJobRegistry(1)
        started, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def work():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleanup.set()
                await release.wait()

        task = registry.start("request", work())
        await started.wait()
        with self.assertLogs("app.services.jobs", level="WARNING"):
            await registry.shutdown(timeout_seconds=0.01)
        self.assertTrue(cleanup.is_set())
        self.assertFalse(task.done())
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
