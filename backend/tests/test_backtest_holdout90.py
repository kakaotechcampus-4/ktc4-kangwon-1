"""시설을 모를 때 가능한 순위 범위와 동점·확인된 실제0의 경계를 검증합니다."""

import itertools
import unittest

from backtest.holdout90 import rank_bounds
from backtest.weight_selection import order_scores


class FacilityRankBoundsTests(unittest.TestCase):
    def ties(self, codes):
        return {c: {"coverage": 1, "adjustment": 0} for c in codes}

    def test_bounds_contain_all_endpoint_rankings(self):
        ranges = {
            "a": {"low": 40, "high": 60},
            "b": {"low": 50, "high": 70},
            "c": {"low": 55, "high": 55},
        }
        ties = self.ties(ranges)
        bounds = rank_bounds(ranges, ties)
        for endpoints in itertools.product(("low", "high"), repeat=3):
            values = {
                c: v[endpoint] for (c, v), endpoint in zip(ranges.items(), endpoints, strict=True)
            }
            order = order_scores(values, ties)
            for code in ranges:
                self.assertLessEqual(bounds[code]["best_rank"], order.index(code) + 1)
                self.assertGreaterEqual(bounds[code]["worst_rank"], order.index(code) + 1)

    def test_known_zero_and_fixed_scores_have_exact_ranks(self):
        ranges = {"a": {"low": 0, "high": 0}, "b": {"low": 80, "high": 80}}
        bounds = rank_bounds(ranges, self.ties(ranges))
        self.assertEqual(bounds["a"], {"best_rank": 2, "worst_rank": 2})
        self.assertEqual(bounds["b"], {"best_rank": 1, "worst_rank": 1})

    def test_ties_keep_coverage_and_adjustment_rules(self):
        ranges = {c: {"low": 50, "high": 50} for c in ("a", "b", "c")}
        ties = self.ties(ranges)
        ties["b"]["coverage"] = 2
        ties["c"]["adjustment"] = 1
        self.assertEqual(rank_bounds(ranges, ties)["c"], {"best_rank": 1, "worst_rank": 1})
        self.assertEqual(rank_bounds(ranges, ties)["b"], {"best_rank": 2, "worst_rank": 2})

    def test_nonfinite_reversed_or_out_of_range_intervals_are_rejected(self):
        for low, high in ((float("nan"), 10), (20, 10), (-1, 10), (0, 91)):
            with self.subTest(low=low, high=high), self.assertRaises(ValueError):
                rank_bounds({"a": {"low": low, "high": high}}, self.ties(["a"]))

    def test_missing_candidate_metadata_cannot_silently_remove_competitor(self):
        with self.assertRaises(ValueError):
            rank_bounds({"a": {"low": 0, "high": 90}}, {})
