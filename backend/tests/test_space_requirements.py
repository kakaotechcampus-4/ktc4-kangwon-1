"""공간 요건 초안의 51업종 범위와 요청별 원문 계보를 검증합니다."""

import asyncio
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agentic.contracts import GetFactsInput
from app.agentic.read_tools import get_facts
from app.agentic.snapshot import persist_space_requirements
from app.db.connection import connect, initialize
from app.db.repository import create_request
from app.industries import DATA_DIR
from app.industries.catalog import INDUSTRIES
from app.storage.raw import capture_scope


class SpaceRequirementsDataTests(unittest.TestCase):
    def test_csv_is_a_complete_unreviewed_draft_with_bom(self):
        path = DATA_DIR / "industry_space_requirements.csv"
        self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 51)
        self.assertEqual({r["industry_code"]: r["industry_name"] for r in rows}, INDUSTRIES)
        for row in rows:
            self.assertEqual(row["reviewed"], "false")
            self.assertEqual(row["confidence"], "low")
            self.assertIn("초안", row["rationale"])
            for key in ("kitchen_needed", "ventilation_needed"):
                self.assertIn(row[key], {"true", "false", "conditional"})
            if row["industry_code"].startswith("G"):
                self.assertEqual(row["kitchen_needed"], "false")
                self.assertEqual(row["ventilation_needed"], "false")
            if row["industry_code"] in {
                "I201",
                "I202",
                "I203",
                "I204",
                "I207",
                "I210",
                "I211",
                "I212",
            }:
                self.assertIn(row["kitchen_needed"], {"true", "conditional"})


class SpaceRequirementsFactsTests(unittest.IsolatedAsyncioTestCase):
    async def test_registration_and_query_keep_raw_row_lineage_and_draft_label(self):
        with tempfile.TemporaryDirectory() as directory:
            path = initialize(Path(directory) / "request.sqlite3")
            create_request("space", "시험", db_path=path)
            async with capture_scope("space", path) as scope:
                await asyncio.to_thread(persist_space_requirements, scope)
                await asyncio.to_thread(persist_space_requirements, scope)
                result = await get_facts(
                    scope,
                    GetFactsInput(
                        industry_code="G204",
                        source="industry_profile",
                        metrics=["space_requirements"],
                    ),
                )
                self.assertEqual(len(result.facts), 1)
                fact = result.facts[0]
                self.assertTrue(fact.citable)
                self.assertFalse(fact.value["reviewed"])
                self.assertEqual(fact.value["kitchen_needed"], "false")
                self.assertIn("검토 전", fact.unit)
                self.assertTrue(fact.provenance_ref.startswith("fact_sources:"))
                with connect(path) as db:
                    self.assertEqual(
                        db.execute(
                            "SELECT count(*) FROM facts WHERE source='industry_profile'"
                        ).fetchone()[0],
                        51,
                    )
                    self.assertEqual(
                        db.execute("SELECT count(*) FROM local_fact_lineage").fetchone()[0], 0
                    )
                    response = db.execute(
                        "SELECT request_args_json FROM raw_responses "
                        "WHERE source='industry_profile'"
                    ).fetchone()
                    self.assertEqual(
                        json.loads(response[0])["file_hash"],
                        hashlib.sha256(
                            (DATA_DIR / "industry_space_requirements.csv").read_bytes()
                        ).hexdigest(),
                    )
                    raw = db.execute(
                        "SELECT r.raw_json FROM fact_sources f "
                        "JOIN raw_rows r USING(raw_row_id) WHERE f.fact_id=?",
                        (fact.fact_id,),
                    ).fetchone()
                    self.assertEqual(json.loads(raw[0])["industry_code"], "G204")

    async def test_invalid_draft_is_rejected_before_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = initialize(folder / "request.sqlite3")
            create_request("invalid", "시험", db_path=path)
            (folder / "industry_space_requirements.csv").write_text(
                "industry_code,industry_name\nG204,종합 소매\n", encoding="utf-8-sig"
            )
            async with capture_scope("invalid", path) as scope:
                with patch("app.agentic.snapshot.DATA_DIR", folder):
                    with self.assertRaises(ValueError):
                        await asyncio.to_thread(persist_space_requirements, scope)
                with connect(path) as db:
                    self.assertEqual(
                        db.execute("SELECT count(*) FROM raw_responses").fetchone()[0], 0
                    )
