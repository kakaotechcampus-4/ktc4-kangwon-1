"""저장된 요청 DB에서 심사 시험 재료를 읽는 동작을 검증합니다."""

import sqlite3
import unittest
from pathlib import Path

from app.agentic.contracts import SubmitDraftInput, SubmitLInput
from app.agentic.runtime import DecisionLoop
from app.schemas import Site
from examiner_eval import store
from tests import test_agentic_runtime as fixtures


class StoreTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.RuntimeTests.asyncSetUp
    asyncTearDown = fixtures.RuntimeTests.asyncTearDown

    async def submit(self):
        loop = await DecisionLoop.create(self.scope, self.site)
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        db = sqlite3.connect(self.path)
        try:
            with db:
                db.execute(
                    "UPDATE analysis_requests SET site_json=? WHERE request_id=?",
                    (self.site.model_dump_json(), self.scope.request_id),
                )
        finally:
            db.close()
        return loop.done.report_id

    async def test_load_contexts_reads_draft_and_citable_facts(self):
        report_id = await self.submit()
        contexts = store.load_contexts(self.path)
        self.assertEqual(len(contexts), 1)
        ctx = contexts[0]
        self.assertEqual(ctx.request_id, self.scope.request_id)
        self.assertEqual(ctx.snapshot_id, self.scope.snapshot_id)
        self.assertEqual(ctx.run_id, self.scope.run_id)
        self.assertIsInstance(ctx.site, Site)
        self.assertEqual(ctx.stored_draft["report_id"], report_id)
        self.assertTrue(ctx.facts)
        db = sqlite3.connect(self.path)
        try:
            for (industry, source, metric), fid in ctx.facts.items():
                row = db.execute(
                    "SELECT industry_code, source, metric, status, citable FROM facts "
                    "WHERE fact_id=?",
                    (fid,),
                ).fetchone()
                self.assertEqual(row, (industry, source, metric, "observed", 1))
        finally:
            db.close()

    async def test_copy_refuses_existing(self):
        dest = Path(self.temp.name) / "copy.sqlite3"
        self.assertEqual(store.copy_store(self.path, dest), dest)
        self.assertTrue(dest.exists())
        with self.assertRaises(FileExistsError):
            store.copy_store(self.path, dest)

    async def test_make_scope_fields(self):
        await self.submit()
        ctx = store.load_contexts(self.path)[0]
        scope = store.make_scope(ctx, self.path)
        self.assertEqual(scope.request_id, ctx.request_id)
        self.assertEqual(scope.snapshot_id, ctx.snapshot_id)
        self.assertEqual(scope.run_id, ctx.run_id)
        self.assertEqual(scope.path, self.path)


if __name__ == "__main__":
    unittest.main()
