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
            excluded = {
                r[0]
                for r in db.execute(
                    "SELECT fact_id FROM facts WHERE request_id=? AND snapshot_id=? "
                    "AND (status<>'observed' OR citable<>1)",
                    (ctx.request_id, ctx.snapshot_id),
                )
            }
            self.assertTrue(excluded)
            self.assertFalse(excluded & set(ctx.facts.values()))
            for (industry, source, metric), fid in ctx.facts.items():
                row = db.execute(
                    "SELECT industry_code, source, metric, status, citable FROM facts "
                    "WHERE fact_id=?",
                    (fid,),
                ).fetchone()
                self.assertEqual(row, (industry, source, metric, "observed", 1))
        finally:
            db.close()

    async def test_load_contexts_reads_close_rate_ratios(self):
        await self.submit()
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM facts WHERE metric='close_rate_ratio' "
                    "ORDER BY industry_code LIMIT 2"
                )
            ]
            with db:
                for index, (row, value) in enumerate(zip(rows, ("1.25", '"없음"'), strict=True)):
                    row.update(
                        fact_id=f"f_ratio-{index}",
                        identity_hash=f"ratio-{index}",
                        status="observed",
                        citable=1,
                        value_json=value,
                    )
                    db.execute(
                        f"INSERT INTO facts({','.join(row)}) VALUES({','.join('?' * len(row))})",
                        list(row.values()),
                    )
        finally:
            db.close()
        ctx = store.load_contexts(self.path)[0]
        codes = [row["industry_code"] for row in rows]
        self.assertEqual(ctx.ratios, {codes[0]: 1.25, codes[1]: None})

    async def test_candidate_facts_keep_every_fact_of_an_industry(self):
        await self.submit()
        contexts = store.load_contexts(self.path)
        ctx = contexts[0]
        (code, source, metric), kept = next(
            (key, fid) for key, fid in ctx.facts.items() if key[0] is not None
        )
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            with db:
                row = dict(db.execute("SELECT * FROM facts WHERE fact_id=?", (kept,)).fetchone())
                row.update(fact_id="f_second-same-key", identity_hash="second-same-key")
                db.execute(
                    f"INSERT INTO facts({','.join(row)}) VALUES({','.join('?' * len(row))})",
                    list(row.values()),
                )
        finally:
            db.close()
        found = store.candidate_facts(self.path, contexts)[ctx.request_id]
        self.assertTrue({kept, "f_second-same-key"} <= found[code])

    async def test_copy_refuses_existing(self):
        dest = Path(self.temp.name) / "copy.sqlite3"
        self.assertEqual(store.copy_store(self.path, dest), dest)
        self.assertTrue(dest.exists())
        with self.assertRaises(FileExistsError):
            store.copy_store(self.path, dest)

    async def test_copy_failure_leaves_no_dest(self):
        dest = Path(self.temp.name) / "missing-copy.sqlite3"
        with self.assertRaises(sqlite3.Error):
            store.copy_store(Path(self.temp.name) / "absent.sqlite3", dest)
        self.assertFalse(dest.exists())

    async def test_skipped_request_logs_warning(self):
        await self.submit()
        db = sqlite3.connect(self.path)
        try:
            with db:
                db.execute("UPDATE analysis_requests SET site_json=NULL")
        finally:
            db.close()
        with self.assertLogs("examiner_eval.store", level="WARNING") as logs:
            contexts = store.load_contexts(self.path)
        self.assertEqual(contexts, [])
        self.assertIn(self.scope.request_id, logs.output[0])

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
