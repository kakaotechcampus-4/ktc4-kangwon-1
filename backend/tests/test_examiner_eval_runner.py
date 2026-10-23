"""심사위원만 돌리는 시험 실행기를 가짜 모델로 검증합니다."""

import asyncio
import contextlib
import copy
import dataclasses
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.agentic import evaluators, examiner
from app.agentic.contracts import SubmitDraftInput, SubmitLInput
from app.agentic.runtime import DecisionLoop
from app.agentic.scoring import WEIGHTS, result, summarize
from app.agentic.snapshot import persist_report
from app.db.connection import initialize
from app.db.repository import create_request
from app.industries.catalog import INDUSTRIES
from app.schemas import Site
from app.storage.raw import capture_scope
from examiner_eval import runner, store
from examiner_eval.cases import dump_cases, load_cases
from examiner_eval.generator import build_cases
from examiner_eval.variants import VARIANTS

SAVE_REVIEW = evaluators.save_review
REVIEW_PACKET = examiner.review_packet
SITE = Site(input_address="시험", road_address="시험", latitude=37.5, longitude=127.0)


async def make_store(folder):
    path = Path(folder) / "source.sqlite3"
    initialize(path)
    create_request("loop", "시험", db_path=path)
    async with capture_scope("loop", path) as scope:
        rows = [
            summarize(code, {key: result(key) for key in WEIGHTS}, "해당 없음")
            for code in INDUSTRIES
        ]
        persist_report(scope, {"rows": rows, "top5": rows[:5]}, {}, [])
        loop = await DecisionLoop.create(scope, SITE)
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
    with contextlib.closing(sqlite3.connect(path)) as db, db:
        db.execute(
            "UPDATE analysis_requests SET site_json=? WHERE request_id=?",
            (SITE.model_dump_json(), "loop"),
        )
    return path


def cited(case, ctx):
    draft = copy.deepcopy(case.draft)
    first = draft["top5"][0]
    fact_id = ctx.facts[(first["industry_code"], "industry_profile", "space_requirements")]
    first["reasons_segments"] = [
        {"type": "text", "text": "공간 요건 초안은 "},
        {"type": "fact", "fact_id": fact_id, "format": "text"},
    ]
    first["fact_ids"] = [fact_id]
    return dataclasses.replace(case, draft=draft), fact_id


def line_count(path):
    return len(Path(path).read_text(encoding="utf-8").splitlines())


class RunCaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        source = await make_store(self.folder)
        self.db = store.copy_store(source, self.folder / "copy.sqlite3")
        self.ctx = store.load_contexts(self.db)[0]
        self.cases = build_cases([self.ctx])

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def execute(self, case, variant="V2", generate=runner.fake_generate, **kwargs):
        return await runner.run_case(
            case, variant, self.ctx, self.db, repeat=1, generate=generate, **kwargs
        )

    async def test_run_case_completes_with_fake_and_counts_calls(self):
        case, _ = cited(self.cases[0], self.ctx)
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                outcome = await self.execute(case, variant)
                self.assertEqual(outcome.status, "completed", outcome.error_code)
                self.assertIsNone(outcome.error_code)
                self.assertEqual(outcome.variant, variant)
                self.assertEqual(outcome.repeat, 1)
                self.assertEqual(outcome.case_id, case.case_id)
                self.assertGreaterEqual(outcome.end_event["model_calls"], 1)
                self.assertEqual(outcome.calls, outcome.end_event["model_calls"])
                self.assertEqual(
                    set(outcome.end_event), {"issues_count", "reads", "rejections", "model_calls"}
                )
                self.assertEqual(outcome.model, runner.FAKE_MODEL)
                self.assertGreaterEqual(outcome.elapsed_ms, 0)
        self.assertIs(examiner.review_packet, REVIEW_PACKET)

    async def test_failed_generation_is_recorded(self):
        async def boom(messages, definitions, settings, receipt):
            raise RuntimeError("boom")

        async def slow(messages, definitions, settings, receipt):
            raise TimeoutError()

        for generate, code in ((boom, "RuntimeError"), (slow, "TIMEOUT")):
            with self.subTest(code=code):
                outcome = await self.execute(self.cases[0], generate=generate)
                self.assertEqual(outcome.status, "failed")
                self.assertEqual(outcome.error_code, code)
                self.assertIsNone(outcome.verdict)
                self.assertEqual(outcome.issues, [])
                self.assertEqual(outcome.calls, 1)

    async def test_records_packet_size(self):
        seen = []

        def spy(messages, definitions, settings, receipt):
            seen.append(messages[1]["content"])
            return runner.fake_generate(messages, definitions, settings, receipt)

        case, _ = cited(self.cases[0], self.ctx)
        outcome = await self.execute(case, generate=spy)
        self.assertGreater(outcome.packet_chars, 0)
        self.assertEqual(outcome.packet_chars, len(seen[0]))
        self.assertEqual(outcome.omitted_fact_ids, len(json.loads(seen[0])["omitted_fact_ids"]))

    async def test_variant_swaps_packet(self):
        seen = {}

        def spy(messages, definitions, settings, receipt):
            seen[variant] = json.loads(messages[1]["content"])
            return runner.fake_generate(messages, definitions, settings, receipt)

        for variant in ("V0", "V2"):
            await self.execute(self.cases[0], variant, generate=spy)
        self.assertIn("top5", seen["V0"])
        self.assertNotIn("candidates", seen["V0"])
        self.assertIn("candidates", seen["V2"])
        self.assertIs(examiner.review_packet, REVIEW_PACKET)

    async def test_issues_hold_real_fact_ids(self):
        sent = []

        def spy(messages, definitions, settings, receipt):
            message = runner.fake_generate(messages, definitions, settings, receipt)
            sent.append(json.loads(message.tool_calls[0].function.arguments))
            return message

        case, fact_id = cited(self.cases[0], self.ctx)
        outcome = await self.execute(case, generate=spy)
        self.assertEqual(outcome.status, "completed", outcome.error_code)
        alias = sent[0]["issues"][0]["fact_ids"][0]
        self.assertNotEqual(alias, fact_id)
        self.assertEqual(len(outcome.issues), 1)
        issue = outcome.issues[0]
        self.assertEqual(issue["kind"], "missing_evidence")
        self.assertEqual(issue["fact_ids"], [fact_id])
        self.assertTrue(issue["issue_id"].startswith("examiner:"))
        self.assertEqual(outcome.verdict, "conditional")
        self.assertEqual(outcome.end_event["issues_count"], 1)
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            row = db.execute(
                "SELECT 1 FROM facts WHERE fact_id=? AND request_id=?",
                (fact_id, self.ctx.request_id),
            ).fetchone()
        self.assertIsNotNone(row)

    async def test_same_request_twice_with_existing_review(self):
        with contextlib.closing(sqlite3.connect(self.db)) as db, db:
            db.execute(
                "INSERT INTO agentic_reviews VALUES(?,?,?,?,?)",
                (self.ctx.request_id, self.ctx.snapshot_id, "examiner", "{}", "2026-10-23"),
            )
        outcomes = [await self.execute(case) for case in self.cases[:2]]
        self.assertEqual([o.status for o in outcomes], ["completed", "completed"])
        self.assertIs(evaluators.save_review, SAVE_REVIEW)
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            count = db.execute("SELECT COUNT(*) FROM agentic_reviews").fetchone()[0]
        self.assertEqual(count, 1)

    async def test_records_calls_to_recorder_path(self):
        path = self.folder / "calls" / "one.json"
        await self.execute(self.cases[0], recorder_path=path)
        entries = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([e["role"] for e in entries], ["examiner"])

    async def test_stops_before_next_case_at_max_calls(self):
        out = self.folder / "out"
        out.mkdir()
        pending = [(self.cases[0], 1), (self.cases[1], 1)]
        with contextlib.redirect_stdout(io.StringIO()):
            results, total, stopped = await runner.run_pending(
                pending,
                {self.ctx.request_id: self.ctx},
                self.db,
                out,
                variant="V2",
                generate=runner.fake_generate,
                model=runner.FAKE_MODEL,
                max_calls=1,
            )
        self.assertTrue(stopped)
        self.assertEqual(len(results), 1)
        self.assertEqual(total, 1)
        self.assertEqual(line_count(out / runner.RESULTS), 1)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.src = asyncio.run(make_store(self.folder))
        self.db = self.folder / "copy.sqlite3"
        self.out = self.folder / "out"
        self.cases = self.out / "cases.json"
        code, printed, _ = self.call("build", "--src", self.src, "--db", self.db, "--out", self.out)
        self.assertEqual(code, 0)
        self.printed = printed

    def tearDown(self):
        self.temp.cleanup()

    def call(self, *argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = runner.main([str(a) for a in argv])
        return code, stdout.getvalue(), stderr.getvalue()

    def run_args(self, out, *extra, variant="V2"):
        return (
            "--db",
            self.db,
            "--cases",
            self.cases,
            "--variant",
            variant,
            "--out",
            out,
            *extra,
        )

    def rows(self, out):
        lines = (out / runner.RESULTS).read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines]

    def test_build_writes_cases_and_refuses_overwrite(self):
        self.assertTrue(self.db.exists())
        cases = load_cases(self.cases)
        self.assertEqual([c.source for c in cases], ["clean", "seeded"])
        self.assertIn("clean 1", self.printed)
        self.assertIn("tune 1", self.printed)
        other = self.folder / "other.sqlite3"
        self.assertEqual(
            self.call("build", "--src", self.src, "--db", other, "--out", self.out)[0], 2
        )
        self.assertFalse(other.exists())
        fresh = self.folder / "fresh"
        self.assertEqual(
            self.call("build", "--src", self.src, "--db", self.db, "--out", fresh)[0], 2
        )
        self.assertEqual(
            self.call("build", "--src", self.src, "--db", self.src, "--out", fresh)[0], 2
        )
        self.assertFalse((fresh / "cases.json").exists())

    def test_resume_skips_done_rows(self):
        out = self.folder / "V2"
        self.assertEqual(self.call(*self.run_args(out, "--fake"))[0], 0)
        first = line_count(out / runner.RESULTS)
        self.assertEqual(first, 3)
        header, *rows = self.rows(out)
        self.assertEqual(
            header,
            {
                "type": "header",
                "variant": "V2",
                "split": "tune",
                "repeats": 1,
                "model": runner.FAKE_MODEL,
                "mode": "fake",
                "max_calls": None,
            },
        )
        self.assertEqual({r["type"] for r in rows}, {"result"})
        self.assertEqual({r["status"] for r in rows}, {"completed"})
        self.assertEqual(self.call(*self.run_args(out, "--fake"))[0], 0)
        self.assertEqual(line_count(out / runner.RESULTS), first)
        self.assertEqual(self.call(*self.run_args(out, "--fake", "--repeats", "2"))[0], 0)
        self.assertEqual(
            sorted((r["case_id"], r["repeat"]) for r in self.rows(out)[1:]),
            sorted((c.case_id, n) for c in load_cases(self.cases) for n in (1, 2)),
        )

    def test_header_mismatch_refused(self):
        out = self.folder / "V2"
        self.assertEqual(self.call(*self.run_args(out, "--fake"))[0], 0)
        before = line_count(out / runner.RESULTS)
        self.assertEqual(self.call(*self.run_args(out, "--fake", variant="V1"))[0], 2)
        self.assertEqual(self.call(*self.run_args(out, "--fake", "--split", "all"))[0], 2)
        self.assertEqual(line_count(out / runner.RESULTS), before)

    def test_real_requires_max_calls_and_refuses_over_budget(self):
        out = self.folder / "real"
        with (
            patch.object(runner, "load_environment", Mock()) as load,
            patch.object(runner, "run_case", AsyncMock()) as run_case,
        ):
            self.assertEqual(self.call(*self.run_args(out, "--real"))[0], 2)
            code, _, err = self.call(*self.run_args(out, "--real", "--max-calls", "1"))
            self.assertEqual(code, 2)
            self.assertIn("12", err)
        load.assert_not_called()
        run_case.assert_not_called()
        self.assertFalse((out / runner.RESULTS).exists())

    def test_real_records_evaluator_model_in_header(self):
        out = self.folder / "real"
        case = load_cases(self.cases)[0]
        done = runner.CaseResult(
            case_id=case.case_id,
            variant="V2",
            repeat=1,
            status="completed",
            error_code=None,
            verdict="agree",
            issues=[],
            end_event={"issues_count": 0, "reads": 0, "rejections": 0, "model_calls": 1},
            calls=1,
            input_tokens=0,
            output_tokens=0,
            elapsed_ms=1,
            model=None,
            packet_chars=1,
            omitted_fact_ids=0,
        )
        env = {
            "EVALUATOR_LLM_MODEL": "eval-model",
            "EVALUATOR_LLM_API_KEY": "placeholder-key",
            "EVALUATOR_LLM_BASE_URL": "http://localhost",
        }
        with (
            patch.dict(os.environ, env),
            patch.object(runner, "load_environment", Mock()) as load,
            patch.object(runner, "run_case", AsyncMock(return_value=done)) as run_case,
        ):
            code, _, err = self.call(*self.run_args(out, "--real", "--max-calls", "12"))
        self.assertEqual(code, 0, err)
        load.assert_called_once_with()
        self.assertIsNone(run_case.call_args.kwargs["generate"])
        header, *rows = self.rows(out)
        self.assertEqual(header["model"], "eval-model")
        self.assertEqual(header["mode"], "real")
        self.assertEqual(header["max_calls"], 12)
        self.assertEqual({r["model"] for r in rows}, {"eval-model"})

    def test_split_defaults_to_tune(self):
        cases = load_cases(self.cases)
        moved = [cases[0], dataclasses.replace(cases[1], split="test")]
        self.cases.unlink()
        dump_cases(moved, self.cases)
        tune = self.folder / "tune"
        self.assertEqual(self.call(*self.run_args(tune, "--fake"))[0], 0)
        self.assertEqual([r["case_id"] for r in self.rows(tune)[1:]], [cases[0].case_id])
        test = self.folder / "test"
        self.assertEqual(self.call(*self.run_args(test, "--fake", "--split", "test"))[0], 0)
        self.assertEqual([r["case_id"] for r in self.rows(test)[1:]], [cases[1].case_id])

    def test_refuses_db_inside_protected_folder(self):
        out = self.folder / "guard"
        with patch.object(runner, "PROTECTED", self.folder):
            self.assertEqual(self.call(*self.run_args(out, "--fake"))[0], 2)
        self.assertFalse((out / runner.RESULTS).exists())


if __name__ == "__main__":
    unittest.main()
