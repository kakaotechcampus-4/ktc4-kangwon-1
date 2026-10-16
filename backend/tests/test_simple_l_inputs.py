"""별칭과 행별 L 검증이 다른 업종을 막지 않는지 확인합니다."""

import tempfile
import unittest
from pathlib import Path

from app.agentic.aliases import decode, decode_report, encode
from app.agentic.facts import register_fact
from app.agentic.runtime import DecisionLoop
from app.agentic.scoring import WEIGHTS, result, summarize
from app.agentic.snapshot import persist_report
from app.db.connection import connect, initialize
from app.db.repository import create_request
from app.industries.catalog import INDUSTRIES
from app.schemas import Site
from app.storage.raw import capture_scope


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
