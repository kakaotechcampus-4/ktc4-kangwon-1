import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from app.agentic import scoring
from app.agentic.scoring import profiles, score_item
from app.agents.floating_population import baseline as population_baseline


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


class C1AgglomerationTests(unittest.TestCase):
    def sample(self, density):
        return {
            "commercial_collection_complete": True,
            "commercial_area": {
                "radius_m": 500,
                "by_middle": [{"code": "I201", "density_per_km2": density}],
            },
            "floating_population": {
                "benchmark": {
                    "mean_daily_per_trade_area": 4 * population_baseline.DAILY_TOTAL_PERCENTILES[50]
                }
            },
        }

    def c1(self, kind, density, sample=None, percentiles=None):
        profile = {"agglomeration": kind} if kind else {}
        data = sample if sample is not None else self.sample(density)
        with patch(
            "app.agentic.scoring.SEOUL_INDUSTRY_DENSITY_PERCENTILES",
            percentiles or {"I201": {50: 10, 95: 30}},
        ):
            return score_item("C1", profile, "I201", data)

    def test_cluster_grades(self):
        for density, grade in [(4, 0), (6, 1), (10, 2), (13, 3), (20, 4), (30, 4), (31, 3)]:
            self.assertEqual(self.c1("모임형", density)["grade"], grade, density)

    def test_saturation_never_below_zero(self):
        out = self.c1("모임형", 4, percentiles={"I201": {50: 10, 95: 3}})
        self.assertEqual(out["grade"], 0)

    def test_cluster_ignores_floating(self):
        sample = self.sample(10)
        sample["floating_population"]["benchmark"]["mean_daily_per_trade_area"] = 0
        self.assertEqual(self.c1("모임형", 10, sample)["status"], "observed")
        sample = self.sample(10)
        sample["runtime_partial_sources"] = ["floating_population"]
        self.assertEqual(self.c1("모임형", 10, sample)["status"], "observed")
        sample = self.sample(10)
        sample["runtime_partial_sources"] = ["commercial_area"]
        self.assertEqual(self.c1("모임형", 10, sample)["status"], "unknown")

    def test_nearby_matches_current(self):
        sample = self.sample(40)
        percentiles = {"I201": {50: 10}}
        near = self.c1("근처형", 40, sample, percentiles)
        missing = self.c1(None, 40, sample, percentiles)
        self.assertEqual(near["value"], 2)
        self.assertEqual(missing["value"], 2)
        self.assertEqual(near["grade"], missing["grade"])
        self.assertTrue(near["reason"].startswith("근처형: "))

    def test_unrelated_is_fixed_middle(self):
        out = self.c1("무관", 10)
        self.assertEqual(out["grade"], 2)
        self.assertEqual(out["points"], 7.5)
        self.assertEqual(out["status"], "observed")
        self.assertIsNone(out["value"])
        self.assertIn("관측값 아님", out["reason"])
        for sample in ({}, {"runtime_partial_sources": ["commercial_area"]}):
            again = self.c1("무관", 10, sample)
            self.assertEqual((again["grade"], again["status"]), (2, "observed"))

    def test_unknown_agglomeration_value_is_an_error(self):
        for value in ("모임 형", "", None, "cluster"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as caught:
                    score_item("C1", {"agglomeration": value}, "I201", self.sample(10))
                self.assertIn("I201", str(caught.exception))
        for profile in ({}, {"agglomeration": "근처형"}):
            self.assertEqual(
                score_item("C1", profile, "I201", self.sample(10))["status"], "observed"
            )

    def test_cluster_reason_keeps_baseline_gap_notice(self):
        self.assertIn("밀도 기준선 시점 차이", self.c1("모임형", 20)["reason"])
        self.assertIn("밀도 기준선 시점 차이", self.c1("모임형", 31)["reason"])

    def test_cluster_reason_mentions_saturation(self):
        self.assertIn("상위 5% 초과", self.c1("모임형", 31)["reason"])
        self.assertNotIn("상위 5% 초과", self.c1("모임형", 20)["reason"])
