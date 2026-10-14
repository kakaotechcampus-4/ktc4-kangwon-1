"""본문 공유와 요청별 계보·실패 진단은 네트워크 없이 검증합니다."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db.connection import connect, initialize
from app.db.repository import create_request, mark_running
from app.storage.raw import capture_scope, scoped_reader


class DedupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = initialize(Path(self.temp.name) / "dedup.sqlite3")
        for name in ("one", "two", "other"):
            create_request(name, "오프라인", db_path=self.path)

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def record(self, scope, page=1, store="same"):
        return await scope.record(
            source="commercial_area",
            source_type="api",
            args={"query": {"pageNo": page}},
            page=str(page),
            status=200,
            payload={"rows": [{"bizesId": store, "name": "원문"}]},
        )

    async def test_shared_body_rows_views_and_lineage(self):
        from app.agents.agentic.facts import register_fact

        scopes = []
        for name in ("one", "two"):
            async with capture_scope(name, self.path) as scope:
                await self.record(scope)
                scopes.append(scope)
        with connect(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM raw_payloads").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM raw_rows").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM raw_responses").fetchone()[0], 2)
        refs = []
        for scope in scopes:
            with scoped_reader(self.path, scope.request_id, scope.snapshot_id) as db:
                rows = db.execute("SELECT raw_row_id,request_id FROM v_raw_stores").fetchall()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0][1], scope.request_id)
                refs.append(rows[0][0])
            fact = register_fact(
                scope,
                industry_code=None,
                source="commercial_area",
                metric="place_name",
                value="원문",
                unit="이름",
                status="observed",
                row_ids=[rows[0][0]],
            )
            self.assertTrue(fact.startswith("f_"))
        self.assertEqual(refs[0], refs[1])
        async with capture_scope("other", self.path) as scope:
            with self.assertRaises(ValueError):
                register_fact(
                    scope,
                    industry_code=None,
                    source="commercial_area",
                    metric="place_name",
                    value="원문",
                    unit="이름",
                    status="observed",
                    row_ids=refs[:1],
                )

    async def test_parallel_writes_are_serialized_and_each_page_atomic(self):
        import app.storage.raw as raw

        original = raw._save_response
        active = 0
        maximum = 0

        def observed(*args, **kwargs):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            try:
                return original(*args, **kwargs)
            finally:
                active -= 1

        async with capture_scope("one", self.path) as scope:
            with patch.object(raw, "_save_response", side_effect=observed):
                await asyncio.gather(*(self.record(scope, i, str(i)) for i in range(12)))
        self.assertEqual(maximum, 1)
        with connect(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM raw_rows").fetchone()[0], 12)

    async def test_failure_diagnostics_scrub_secrets_and_keep_public_message(self):
        from app.services.agentic_analysis import _failure

        mark_running("one", db_path=self.path)
        with patch.dict("os.environ", {"ELICE_API_KEY": "private-key"}):
            await _failure(self.path, "one", OSError("private-key https://x/private-key"), "수집")
        with connect(self.path) as db:
            error, details = db.execute(
                "SELECT error_json,diagnostics_json FROM decision_failures"
            ).fetchone()
            self.assertNotIn("private-key", details)
            self.assertNotIn("https://", details)
            diagnostic = json.loads(details)[0]
            self.assertEqual(diagnostic["exception_class"], "OSError")
            self.assertEqual(diagnostic["stage"], "수집")
            self.assertEqual(json.loads(error)["message"], "새 판단 실행을 완료하지 못했습니다.")

    async def test_failed_page_rolls_back_body_rows_and_links(self):
        from app.storage.raw import RawStorageError

        async with capture_scope("one", self.path) as scope:
            with patch("app.storage.raw._natural", side_effect=ValueError("행 오류")):
                with self.assertRaises(RawStorageError) as error:
                    await self.record(scope)
            self.assertIsInstance(error.exception.__cause__, ValueError)
        with connect(self.path) as db:
            for table in ("raw_payloads", "raw_rows", "raw_responses", "raw_response_rows"):
                self.assertEqual(db.execute("SELECT count(*) FROM " + table).fetchone()[0], 0)

    async def test_lineage_validation_reads_references_in_batches(self):
        from app.agents.agentic.facts import register_fact

        async with capture_scope("one", self.path) as scope:
            await scope.record(
                source="commercial_area",
                source_type="api",
                args={},
                page="1",
                status=200,
                payload={"rows": [{"bizesId": str(i)} for i in range(100)]},
            )
            with connect(self.path) as db:
                refs = [r[0] for r in db.execute("SELECT raw_row_id FROM raw_rows")]
                queries = []
                db.set_trace_callback(
                    lambda sql: (
                        queries.append(sql)
                        if sql.startswith("SELECT") and "raw_response_rows" in sql
                        else None
                    )
                )
                register_fact(
                    scope,
                    industry_code=None,
                    source="commercial_area",
                    metric="store_count",
                    value=100,
                    unit="개",
                    status="observed",
                    row_ids=refs,
                    connection=db,
                )
                self.assertLessEqual(len(queries), 2)

    async def test_cancelled_write_notifies_worker_and_waits_for_exit(self):
        from threading import Event

        from app.storage.raw import _write

        started, stop, finished = Event(), Event(), Event()

        def worker():
            started.set()
            stop.wait()
            finished.set()
            raise asyncio.CancelledError()

        task = asyncio.create_task(_write(worker, on_cancel=stop.set))
        await asyncio.to_thread(started.wait, 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(finished.is_set())

    async def test_service_failure_records_scoring_and_loop_stage(self):
        from contextlib import nullcontext

        from app.services.agentic_analysis import execute_agentic_analysis
        from app.services.agentic_mock import dependencies

        async def generate(*args):
            raise OSError("모델 대역 오류")

        for stage in ("채점", "루프"):
            mocked = (
                patch(
                    "app.services.agentic_analysis.persist_snapshot_scores",
                    side_effect=OSError("채점 오류"),
                )
                if stage == "채점"
                else nullcontext()
            )
            with mocked, self.assertRaises(OSError):
                await execute_agentic_analysis(
                    "오프라인",
                    request_id=stage,
                    db_path=self.path,
                    **(dependencies() | {"generate": generate}),
                )
            with connect(self.path) as db:
                details = json.loads(
                    db.execute(
                        "SELECT diagnostics_json FROM decision_failures WHERE request_id=?",
                        (stage,),
                    ).fetchone()[0]
                )
                self.assertEqual(details[0]["stage"], stage)
