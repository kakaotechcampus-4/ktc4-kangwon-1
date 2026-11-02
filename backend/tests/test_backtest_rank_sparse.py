"""소량 관측의 할인·원문 검증과 실제 관측/추정 구분을 확인합니다."""

import copy
import unittest

from backtest.rank_sparse import apply_sparse, reliability, sparse_evidence
from backtest.temporal_score import metrics


def inputs(stores=None, closed=None):
    stores = stores if stores is not None else [2] * 12
    closed = closed if closed is not None else [0] * 12
    opened = [0] * 12
    local = metrics(list(zip(stores, opened, closed, strict=True)))
    local["avg_store_count"] = sum(stores) / 12
    city = {
        "recent_year_close_rate": 2.0,
        "oldest_year_close_rate": 2.0,
        "turnover_rate": 5.0,
        "net_change_rate": 0.0,
        "data_complete": True,
        "zero_filled_sources": 0,
    }
    calibration = {"cutoff": "20252", "quarter_count": 12, "lifecycle": {"I201": city}}
    row = {"code": "I201", "items": {n: {"status": "unknown"} for n in ("S1", "S2", "S3", "S4")}}
    series = {
        "industry_id": "I201",
        "zero_filled_sources": 0,
        "store_counts": stores,
        "opened_counts": opened,
        "closed_counts": closed,
    }
    data = {
        "business_lifecycle": {
            "metadata": {"base_quarter": "20252", "quarter_count": 12},
            "industries": [
                {
                    "industry_id": "I201",
                    "data_complete": True,
                    "zero_filled_sources": 0,
                    "metrics": local,
                }
            ],
        },
        "lifecycle_quarterly": {
            "quarters": [
                "20223",
                "20224",
                "20231",
                "20232",
                "20233",
                "20234",
                "20241",
                "20242",
                "20243",
                "20244",
                "20251",
                "20252",
            ],
            "industries": [series],
        },
    }
    return row, data, calibration


class SparseRankTests(unittest.TestCase):
    def test_reliability_keeps_disadvantage_and_is_continuous_at_gate(self):
        for power in (1, 2):
            values = [reliability(n, power) for n in range(42)]
            self.assertEqual(values, sorted(values))
            self.assertEqual(values[0], 0)
            self.assertEqual(values[40:], [1, 1])
            self.assertAlmostEqual(reliability(40 - 1e-8, power), 1, places=8)
            self.assertLess(values[12], 0.31)
        self.assertLess(reliability(12, 2), reliability(12, 1))

    def test_gate_uses_comparison_windows_and_does_not_invent_undefined_trend(self):
        row, data, calibration = inputs()
        evidence = sparse_evidence(row, data, calibration)
        self.assertEqual(set(evidence["eligible"]), {"S1", "S2", "S3"})
        self.assertEqual(evidence["eligible"]["S1"]["exposure"], 24)
        self.assertEqual(evidence["eligible"]["S2"]["exposure"], 8)
        self.assertEqual(evidence["skipped"]["S4"], "undefined_rate_denominator")

    def test_actual_old_and_recent_closures_can_support_trend_estimate(self):
        row, data, calibration = inputs(closed=[1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0])
        self.assertIn("S4", sparse_evidence(row, data, calibration)["eligible"])

    def test_no_estimate_for_unsupported_incomplete_or_zero_filled_source(self):
        row, data, calibration = inputs()
        unsupported = {**row, "code": "S208"}
        self.assertFalse(sparse_evidence(unsupported, data, calibration)["eligible"])
        for field, value in (("data_complete", False), ("zero_filled_sources", 1)):
            changed = copy.deepcopy(data)
            changed["business_lifecycle"]["industries"][0][field] = value
            self.assertFalse(sparse_evidence(row, changed, calibration)["eligible"])
        row, data, calibration = inputs(stores=[0] * 12)
        self.assertFalse(sparse_evidence(row, data, calibration)["eligible"])

    def test_wrong_period_malformed_counts_and_metric_disagreement_are_not_hidden(self):
        row, data, calibration = inputs()
        changed = copy.deepcopy(data)
        changed["business_lifecycle"]["metadata"]["base_quarter"] = "20262"
        with self.assertRaises(ValueError):
            sparse_evidence(row, changed, calibration)
        changed = copy.deepcopy(data)
        changed["lifecycle_quarterly"]["industries"][0]["closed_counts"][0] = -1
        with self.assertRaises(ValueError):
            sparse_evidence(row, changed, calibration)
        changed = copy.deepcopy(data)
        changed["business_lifecycle"]["industries"][0]["metrics"]["turnover_rate"] = 99
        with self.assertRaises(ValueError):
            sparse_evidence(row, changed, calibration)

    def test_observed_items_and_other_domains_are_preserved_without_mutation(self):
        row, data, calibration = inputs()
        row["items"]["S1"]["status"] = "observed"
        original = copy.deepcopy((row, data, calibration))
        evidence = sparse_evidence(row, data, calibration)
        base = {
            "points": 10,
            "normalized": 10,
            "applicable": 80,
            "item_points": {"D1": 7.5, "C1": 0, "S1": 2.5, "S2": None, "S3": None, "S4": None},
            "item_grades": {"D1": 3, "C1": 0, "S1": 4 / 3},
        }
        base_copy = copy.deepcopy(base)
        adjusted = apply_sparse(base, evidence, power=1, curve="stored")
        self.assertNotIn("S1", adjusted["estimated_item_points"])
        self.assertEqual(adjusted["item_points"], base["item_points"])
        self.assertEqual(adjusted["item_grades"], base["item_grades"])
        self.assertEqual(adjusted["applicable"], 80)
        self.assertGreater(adjusted["estimated_points"], 0)
        self.assertEqual(base, base_copy)
        self.assertEqual((row, data, calibration), original)

    def test_estimates_never_exceed_undiscounted_grade_points(self):
        row, data, calibration = inputs()
        evidence = sparse_evidence(row, data, calibration)
        base = {
            "points": 0,
            "normalized": 0,
            "applicable": 80,
            "item_points": {n: None for n in row["items"]},
        }
        for curve in ("stored", "ratio"):
            linear = apply_sparse(base, evidence, power=1, curve=curve)
            squared = apply_sparse(base, evidence, power=2, curve=curve)
            self.assertLessEqual(squared["estimated_points"], linear["estimated_points"])
            for name, points in linear["estimated_item_points"].items():
                grade = linear["estimate_evidence"][name]["undiscounted_grade"]
                self.assertLessEqual(points, 7.5 * grade / 4)
                self.assertLess(points, 7.5)


if __name__ == "__main__":
    unittest.main()
