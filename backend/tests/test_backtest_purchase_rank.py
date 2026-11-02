"""분포 차이 보완이 동률·결측·기존 점수 범위를 왜곡하지 않는지 검증합니다."""

import unittest
from statistics import mean
from types import SimpleNamespace

from app.agents.floating_population.models import AGE_BANDS
from backtest.purchase_rank import correction, distribution_for


class PurchaseRankTests(unittest.TestCase):
    def test_uniform_industry_mean_delta_is_zero_on_same_unlabelled_reference(self):
        pairs = [(i / 10, (i % 7) / 10) for i in range(30)]
        changes = [correction(0.5, a, b, pairs, 0.5)["delta"] for a, b in pairs]
        self.assertAlmostEqual(mean(changes), 0)

    def test_same_rank_gives_no_bonus_and_small_reference_is_withheld(self):
        pairs = [(i / 10, i / 10) for i in range(20)]
        result = correction(0.3, 0.5, 0.5, pairs, 0.25)
        self.assertEqual(result["fraction"], 0.3)
        self.assertFalse(correction(0.3, 0.5, 0.5, pairs[:19], 0.25)["available"])

    def test_bounds_are_recorded_and_missing_or_invalid_pairs_rejected(self):
        pairs = [(i / 20, i / 20) for i in range(20)]
        result = correction(0.9, 0, 1, pairs, 0.5)
        self.assertEqual(result["fraction"], 1)
        self.assertTrue(result["clipped"])
        with self.assertRaises(ValueError):
            correction(0.5, 1, 1, [(1, None)] * 20, 0.5)

    def test_missing_actual_age_bin_is_withheld_and_zero_is_preserved(self):
        record = SimpleNamespace(total=500, by_age={a: 100 for a in AGE_BANDS})
        record.by_age["10"] = 0
        self.assertEqual(distribution_for(["a"], {"a": record})["shares"]["10"], 0)
        record.by_age["20"] = None
        self.assertFalse(distribution_for(["a"], {"a": record})["available"])


if __name__ == "__main__":
    unittest.main()
