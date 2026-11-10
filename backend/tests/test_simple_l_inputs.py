"""별칭과 행별 L 검증이 다른 업종을 막지 않는지 확인합니다."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.ai.aliases import decode, decode_report, encode
from app.ai.runtime import DecisionLoop
from app.application.answers import save_confirmed_space
from app.application.facts import register_fact
from app.application.snapshot import persist_report
from app.domain.industries.catalog import INDUSTRIES
from app.domain.schemas import Site
from app.domain.scoring import WEIGHTS, result, summarize
from app.infrastructure.persistence.connection import connect, initialize
from app.infrastructure.persistence.raw_capture import capture_scope
from app.infrastructure.persistence.repository import create_request


class SimpleLTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = initialize(Path(self.temp.name) / "requests.sqlite3")
        create_request("simple", "시험", db_path=self.path)
        self.manager = capture_scope("simple", self.path)
        self.scope = await self.manager.__aenter__()
        rows = [
            summarize(code, {key: result(key) for key in WEIGHTS}, "해당 없음")
            for code in INDUSTRIES
        ]
        persist_report(self.scope, {"rows": rows, "top5": rows[:5]}, {}, [])
        self.site = Site(input_address="시험", road_address="시험", latitude=37.5, longitude=127.0)
        self.loop = await DecisionLoop.create(self.scope, self.site)

    async def asyncTearDown(self):
        await self.manager.__aexit__(None, None, None)
        self.temp.cleanup()

    async def fact(self, code, value=None):
        with connect(self.path) as db:
            parent = db.execute(
                "SELECT fact_id FROM facts WHERE industry_code=? AND metric='space_requirements'",
                (code,),
            ).fetchone()[0]
        fid = register_fact(
            self.scope,
            industry_code=code,
            source="industry_profile",
            metric="space_fit",
            value=value or {"area": "일치"},
            unit="공간",
            status="observed",
            row_ids=[],
            parent_fact_ids=[parent],
        )
        await self.loop.tools.execute("get_facts", {"fact_ids": [fid]})
        return fid, encode(self.scope, {"fact_id": fid})["fact_id"]

    async def test_unique_stable_aliases_and_unknown(self):
        first, short = await self.fact("G203")
        second, other = await self.fact("G208")
        self.assertEqual(len(short), 8)
        self.assertNotEqual(short, other)
        self.assertEqual(
            decode(self.scope, {"fact_ids": [short, other]})["fact_ids"], [first, second]
        )
        self.assertEqual(encode(self.scope, {"fact_id": short})["fact_id"], short)
        with self.assertRaisesRegex(ValueError, "존재하지 않는 fact: deadbeef"):
            decode(self.scope, {"fact_id": "deadbeef"})

    async def test_record_partial_accept_duplicate_ignore_and_numeric_note(self):
        _, short = await self.fact("G203")
        reply = await self.loop.tools.execute(
            "submit_l",
            {
                "L_records": [
                    {
                        "industry_code": "G203",
                        "factors": [{"fact_id": short, "direction": "favorable"}],
                        "note": "면적 40㎡",
                    },
                    {
                        "industry_code": "G208",
                        "factors": [{"fact_id": "deadbeef", "direction": "adverse"}],
                    },
                ]
            },
        )
        data = reply.data.model_dump()
        self.assertEqual(data["accepted"], ["G203"])
        self.assertEqual(data["rejected"][0]["industry_code"], "G208")
        self.assertIn("G208", data["unsubmitted"])
        self.assertEqual(self.loop.state["L_records"]["G203"]["grade"], 3)
        self.assertTrue(reply.warnings)
        duplicate = await self.loop.tools.execute(
            "submit_l", {"L_records": [{"industry_code": "G203"}]}
        )
        self.assertEqual(duplicate.data.ignored, ["G203"])

    async def test_neutral_unknown_and_more_than_seventeen(self):
        _, short = await self.fact("G203")
        reply = await self.loop.tools.execute(
            "submit_l",
            {
                "L_records": [
                    {
                        "industry_code": code,
                        **({"neutral": True, "fact_ids": [short]} if code == "G203" else {}),
                    }
                    for code in INDUSTRIES
                ]
            },
        )
        self.assertEqual(len(reply.data.accepted), 51)
        self.assertTrue(reply.data.closed)
        self.assertEqual(self.loop.state["L_records"]["G203"]["grade"], 2)
        self.assertEqual(self.loop.state["L_records"]["G208"]["status"], "unknown")

    async def test_unknown_fact_sentence_only_removed(self):
        fid, short = await self.fact("G203")
        body, warnings = decode_report(
            self.scope,
            {
                "phase": "draft",
                "report": {
                    "summary_segments": [
                        {"type": "text", "text": "검토"},
                        {"type": "fact", "fact_id": short, "format": "text"},
                        {"type": "fact", "fact_id": "deadbeef", "format": "text"},
                    ]
                },
            },
        )
        self.assertEqual(len(body["report"]["summary_segments"]), 2)
        self.assertEqual(body["report"]["summary_segments"][1]["fact_id"], fid)
        self.assertIn("deadbeef", warnings[0])

    async def test_report_fills_missing_format_for_registered_fact(self):
        fid, short = await self.fact("G203")
        await self.loop.tools.execute("submit_l", {"finish": True})
        reply = await self.loop.tools.execute(
            "submit_draft",
            {
                "phase": "draft",
                "report": {"summary_segments": [{"type": "fact", "fact_id": short}]},
            },
        )
        self.assertEqual(reply.status, "ok")
        segment = self.loop.done.summary_segments[0]
        self.assertEqual((segment.fact_id, segment.format), (fid, "text"))
        self.assertTrue(any("표시 형식" in warning for warning in reply.warnings))
        self.assertFalse(
            any(
                s.type == "text" and "미등록 근거" in s.text
                for s in self.loop.done.limitations_segments
            )
        )

    async def test_report_references_exact_confirmed_floor_and_area(self):
        saved = save_confirmed_space(self.scope, {"floor": "1층", "exclusive_area": "41㎡"})
        await self.loop.tools.execute("submit_l", {"finish": True})
        reply = await self.loop.tools.execute(
            "submit_draft",
            {
                "phase": "draft",
                "report": {
                    "summary_segments": [{"type": "text", "text": "확인된 1층 공간은 41㎡입니다."}]
                },
            },
        )
        self.assertEqual(reply.status, "ok")
        references = [s.fact_id for s in self.loop.done.summary_segments if s.type == "fact"]
        self.assertEqual(
            references, [saved["fact_ids"]["floor"], saved["fact_ids"]["exclusive_area"]]
        )
        self.assertFalse(
            any(
                char.isnumeric()
                for s in self.loop.done.summary_segments
                if s.type == "text"
                for char in s.text
            )
        )
        with connect(self.path) as db:
            rendered = json.loads(
                db.execute("SELECT rendered_json FROM agentic_reports").fetchone()[0]
            )
        self.assertIn("1층", rendered["summary"])
        self.assertIn("41㎡", rendered["summary"])

    async def test_unverified_report_numbers_stay_rejected(self):
        save_confirmed_space(self.scope, {"floor": "1층", "exclusive_area": "41㎡"})
        await self.loop.tools.execute("submit_l", {"finish": True})
        for text in ("11층", "지하 1층", "-1층", "141㎡", "41.5㎡", "41평", "매출 41만원"):
            with self.subTest(text=text):
                reply = await self.loop.tools.execute(
                    "submit_draft",
                    {
                        "phase": "draft",
                        "report": {"summary_segments": [{"type": "text", "text": text}]},
                    },
                )
                self.assertEqual(reply.error.code, "L_EVIDENCE_INVALID")
                self.assertIn("summary_segments.0", reply.error.message)

    async def test_report_does_not_reuse_older_confirmed_floor(self):
        with patch("app.application.facts.utc_now_iso", return_value="2026-11-11T00:00:00Z"):
            save_confirmed_space(self.scope, {"floor": "1층"})
        with patch("app.application.facts.utc_now_iso", return_value="2026-11-11T00:00:01Z"):
            latest = save_confirmed_space(self.scope, {"floor": "2층"})
        await self.loop.tools.execute("submit_l", {"finish": True})
        old_reply = await self.loop.tools.execute(
            "submit_draft",
            {
                "phase": "draft",
                "report": {"summary_segments": [{"type": "text", "text": "1층입니다."}]},
            },
        )
        self.assertEqual(old_reply.error.code, "L_EVIDENCE_INVALID")
        reply = await self.loop.tools.execute(
            "submit_draft",
            {
                "phase": "draft",
                "report": {"summary_segments": [{"type": "text", "text": "2층입니다."}]},
            },
        )
        self.assertEqual(reply.status, "ok")
        self.assertEqual(self.loop.done.summary_segments[0].fact_id, latest["fact_ids"]["floor"])
