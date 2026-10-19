import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from app.agentic import scoring
from app.agentic.scoring import profiles


class AgglomerationProfileTests(unittest.TestCase):
    def test_every_industry_has_a_type(self):
        rows = profiles()
        self.assertEqual(len(rows), 51)
        self.assertEqual(
            Counter(r["agglomeration"] for r in rows.values()),
            {"모임형": 23, "근처형": 18, "무관": 10},
        )
        self.assertTrue(
            all(r["agglomeration_confidence"] in {"high", "low"} for r in rows.values())
        )
        self.assertTrue(all(r["agglomeration_rationale"].strip() for r in rows.values()))

    def test_known_examples(self):
        rows = profiles()
        for code, kind in {
            "I201": "모임형",
            "P105": "모임형",
            "G210": "모임형",
            "G208": "모임형",
            "G204": "근처형",
            "G215": "근처형",
            "S209": "근처형",
            "M103": "무관",
            "I207": "무관",
        }.items():
            self.assertEqual(rows[code]["agglomeration"], kind, code)
        self.assertEqual(rows["I201"]["agglomeration_confidence"], "high")
        self.assertEqual(rows["G210"]["agglomeration_confidence"], "low")

    def rewrite(self, column, value):
        source = scoring.DATA_DIR / "industry_profile.csv"
        with source.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames
            rows = list(reader)
        rows[0][column] = value
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with (Path(tmp.name) / "industry_profile.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return Path(tmp.name), rows[0]["industry_code"]

    def test_invalid_values_are_rejected(self):
        cases = [
            ("agglomeration", "모임 형"),
            ("agglomeration", ""),
            ("agglomeration_confidence", "medium"),
            ("agglomeration_rationale", "  "),
        ]
        for column, value in cases:
            with self.subTest(column=column, value=value):
                folder, code = self.rewrite(column, value)
                with patch.object(scoring, "DATA_DIR", folder):
                    with self.assertRaises(ValueError) as caught:
                        profiles()
                self.assertIn(code, str(caught.exception))
