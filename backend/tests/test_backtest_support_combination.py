"""S2·D3 결합이 다른 항목이나 원문 상태를 변경하지 않는지 검증합니다."""

import unittest

from backtest.support_combination import combine


class SupportCombinationTests(unittest.TestCase):
    def fixture(self):
        return (
            {"S1": 0.8, "S2": 0.2, "D3": 0.5, "C1": 0.4},
            {"S1": "observed", "S2": "unknown", "D3": "observed", "C1": "observed"},
            {
                "kind": "derived_full_period_estimate_not_new_observation",
                "source_status": "unknown",
                "fraction": 0.6,
            },
            {"D3_rank_half": {"available": True, "fraction": 0.7}},
        )

    def test_half_support_retains_part_of_original_discount_and_other_items(self):
        original, statuses, support, corrections = self.fixture()
        result = combine(original, statuses, support, corrections, "S2_half")
        self.assertAlmostEqual(result["S2"], 0.4)
        self.assertEqual(result["S1"], original["S1"])
        self.assertEqual(result["D3"], original["D3"])
        self.assertEqual(statuses["S2"], "unknown")

    def test_missing_new_evidence_keeps_original_contributions(self):
        original, statuses, _, _ = self.fixture()
        self.assertEqual(combine(original, statuses, None, {}, "S2_full_D3_half"), original)

    def test_full_support_and_rank_correction_are_separate(self):
        original, statuses, support, corrections = self.fixture()
        result = combine(original, statuses, support, corrections, "S2_full_D3_half")
        self.assertAlmostEqual(result["S2"], 0.6)
        self.assertEqual(result["D3"], 0.7)
        self.assertEqual(result["C1"], original["C1"])

    def test_unknown_D3_or_unverified_S2_cannot_receive_new_credit(self):
        original, statuses, support, corrections = self.fixture()
        statuses["D3"] = "unknown"
        with self.assertRaises(ValueError):
            combine(original, statuses, support, corrections, "S2_full_D3_half")
        support["kind"] = "source_rows_missing"
        with self.assertRaises(ValueError):
            combine(original, statuses, support, {}, "S2_full")


if __name__ == "__main__":
    unittest.main()
