"""수요 규모 보정이 실제 인구·관측 0·미확인을 구분하는지 확인합니다."""

import unittest

from backtest.competition_demand import competition_fraction


class CompetitionDemandTests(unittest.TestCase):
    def reference(self):
        return [(5, 100)] * 20 + [(5, 10000)] * 20

    def test_same_store_count_has_less_competition_burden_with_more_demand(self):
        low = competition_fraction(5, 100, self.reference(), "근처형", "near_sqrt")
        high = competition_fraction(5, 10000, self.reference(), "근처형", "near_sqrt")
        self.assertGreater(high["profile_fraction"], low["profile_fraction"])

    def test_near_only_does_not_change_agglomeration_direction_or_rank(self):
        baseline = competition_fraction(5, 100, self.reference(), "모임형", "count")
        changed = competition_fraction(5, 100, self.reference(), "모임형", "near_sqrt")
        self.assertEqual(baseline, changed)

    def test_missing_or_zero_population_does_not_become_fake_observed_demand(self):
        for daily in (None, 0, float("nan")):
            result = competition_fraction(5, daily, self.reference(), "근처형", "near_sqrt")
            self.assertFalse(result["available"])

    def test_actual_zero_stores_is_valid_with_observed_positive_demand(self):
        result = competition_fraction(0, 100, self.reference(), "근처형", "near_sqrt")
        self.assertTrue(result["available"])
        self.assertEqual(result["profile_fraction"], 1)

    def test_equal_counts_keep_the_same_midrank_without_demand_mode(self):
        result = competition_fraction(5, None, self.reference(), "근처형", "count")
        self.assertEqual(result["quantile"], 0.5)
        self.assertEqual(result["reference_n"], 40)

    def test_insufficient_population_matched_references_are_not_imputed(self):
        result = competition_fraction(5, 100, [(1, None)] * 40, "근처형", "all_sqrt")
        self.assertFalse(result["available"])


if __name__ == "__main__":
    unittest.main()
