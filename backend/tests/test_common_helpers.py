"""공용 함수 분리 전후의 직렬화·취소·시간·보간 규칙을 확인합니다."""

import asyncio
import hashlib
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

from app.agents.commercial_area import baseline as density
from app.agents.floating_population import baseline as floating
from app.canonical import canonical_hash, canonical_json, file_sha256
from app.clock import utc_now_iso
from app.concurrency import run_in_thread
from app.stats import percentile_rank


class CommonHelperTests(unittest.TestCase):
    def test_canonical_json_and_hash_preserve_rules(self):
        value = {"z": "한글", "a": [1, None]}
        self.assertEqual(canonical_json(value), '{"a":[1,null],"z":"한글"}')
        self.assertEqual(canonical_hash(value), canonical_hash({"a": [1, None], "z": "한글"}))
        self.assertEqual(
            canonical_hash(value), hashlib.sha256(canonical_json(value).encode()).hexdigest()
        )
        with self.assertRaises(ValueError):
            canonical_json(float("nan"))

    def test_file_hash_and_UTC_iso(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample"
            data = b"data\x00" * 300000
            path.write_bytes(data)
            self.assertEqual(file_sha256(path), hashlib.sha256(data).hexdigest())
        stamp = datetime.fromisoformat(utc_now_iso())
        self.assertEqual(stamp.tzinfo, UTC)

    def test_interpolation_keeps_each_baseline_endpoint_policy(self):
        thresholds = {5: 100.0, 10: 200.0, 95: 1900.0}
        self.assertEqual(percentile_rank(150, thresholds), 7.5)
        self.assertEqual(percentile_rank(0, thresholds), 5)
        self.assertEqual(percentile_rank(2000, thresholds), 95)
        self.assertEqual(floating._percentile(0, thresholds), 5)
        self.assertEqual(floating._percentile(1900, thresholds), 95)
        self.assertEqual(floating._percentile(2000, thresholds), 99)
        self.assertEqual(floating._percentile(float("nan"), thresholds), 99)
        self.assertEqual(density._percentile((100.0, 200.0), 0), 0)
        self.assertEqual(density._percentile((100.0, 200.0), 100), 5)
        self.assertEqual(density._percentile((100.0, 200.0), 150), 7.5)
        self.assertEqual(density._percentile((100.0, 200.0), 200), 100)
        with self.assertRaises(ValueError):
            percentile_rank(0, {})


class ThreadHelperTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_error_propagates(self):
        def worker():
            raise OSError("저장 실패")

        with self.assertRaisesRegex(OSError, "저장 실패"):
            await run_in_thread(worker)

    async def test_cancellation_waits_for_worker(self):
        started, stop, finished = Event(), Event(), Event()

        def worker():
            started.set()
            stop.wait(5)
            finished.set()

        task = asyncio.create_task(run_in_thread(worker, on_cancel=stop.set))
        self.assertTrue(await asyncio.to_thread(started.wait, 1))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(finished.is_set())
