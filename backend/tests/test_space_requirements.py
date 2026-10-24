"""공간 요건 초안의 51업종 범위와 요청별 원문 계보를 검증합니다."""

import asyncio
import csv
import hashlib
import json
import re
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

FACILITY_LEVELS = {"required", "preferred", "conditional", "false"}
FLOOR_LEVELS = {"ground_required", "ground_preferred", "basement_preferred", "false"}


def _numbers(*parts):
    found = set()
    for part in parts:
        if isinstance(part, tuple):
            found.update(range(part[0], part[1] + 1))
        else:
            found.add(part)
    return found


EXPECTED = {
    "kitchen_needed": {"required": _numbers((20, 24), 46), "conditional": _numbers(25, 26)},
    "ventilation_needed": {
        "required": _numbers((20, 24), 41, 45, 46),
        "preferred": _numbers(42),
        "conditional": _numbers(18, 19, 25, 26, 30, 32, 35, 36, 37, 38, 39, 40, 43, 44, 48, 50, 51),
    },
    "water_supply_needed": {
        "required": _numbers(15, 18, 19, (20, 26), 30, 36, 41, 44, 45, 46, 51),
    },
    "floor_preference": {
        "ground_required": _numbers(41, 42),
        "ground_preferred": _numbers((1, 9), (11, 15), 17, 24, 26),
        "basement_preferred": _numbers(38, 39, 51),
    },
}


def _rows():
    path = DATA_DIR / "industry_space_requirements.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class SpaceRequirementsDataTests(unittest.TestCase):
    def test_requirement_values_use_new_vocabulary(self):
        path = DATA_DIR / "industry_space_requirements.csv"
        self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
        rows = _rows()
        self.assertEqual(len(rows), 51)
        self.assertEqual({r["industry_code"]: r["industry_name"] for r in rows}, INDUSTRIES)
        for row in rows:
            with self.subTest(code=row["industry_code"]):
                self.assertEqual(row["reviewed"], "true")
                self.assertEqual(row["confidence"], "low")
                self.assertNotIn("초안", row["rationale"])
                for key in ("kitchen_needed", "ventilation_needed", "water_supply_needed"):
                    self.assertIn(row[key], FACILITY_LEVELS)
                self.assertIn(row["floor_preference"], FLOOR_LEVELS)

    def test_reviewed_cells_match_spec(self):
        rows = _rows()
        for number, row in enumerate(rows, 1):
            for key, levels in EXPECTED.items():
                expected = next((level for level, ns in levels.items() if number in ns), "false")
                with self.subTest(number=number, name=row["industry_name"], key=key):
                    self.assertEqual(row[key], expected)
        by_number = dict(enumerate((r["industry_name"] for r in rows), 1))
        self.assertEqual(by_number[20], "한식 음식점")
        self.assertEqual(by_number[41], "자동차 수리·세차")
        self.assertEqual(by_number[42], "모터사이클 수리")
        self.assertEqual(by_number[10], "의약품·의료기기 소매")
        self.assertEqual(by_number[51], "욕탕·마사지·신체관리 서비스")


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
                self.assertTrue(fact.value["reviewed"])
                self.assertEqual(fact.value["kitchen_needed"], "false")
                self.assertEqual(fact.unit, "공간 요건(시설·층 검토, 면적 추정)")
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

    async def test_rejects_old_vocabulary(self):
        source = (DATA_DIR / "industry_space_requirements.csv").read_text(encoding="utf-8-sig")
        for pattern, replacement in (
            (r",required,", ",true,"),
            (r",ground_preferred,", ",1층 접근 우선 가정,"),
            (r",true(\r?\n)", r",false\1"),
        ):
            with self.subTest(pattern=pattern), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                changed = re.sub(pattern, replacement, source, count=1)
                self.assertNotEqual(changed, source)
                (folder / "industry_space_requirements.csv").write_text(
                    changed, encoding="utf-8-sig"
                )
                path = initialize(folder / "request.sqlite3")
                create_request("old", "시험", db_path=path)
                async with capture_scope("old", path) as scope:
                    with patch("app.agentic.snapshot.DATA_DIR", folder):
                        with self.assertRaises(ValueError):
                            await asyncio.to_thread(persist_space_requirements, scope)

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
