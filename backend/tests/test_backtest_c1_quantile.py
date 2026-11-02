"""백분위 동점과 단봉형 가정·원천 검증을 확인합니다."""

import unittest

from backtest.c1_quantile import profile_fraction


class C1QuantileTests(unittest.TestCase):
    def test_tied_zero_counts_get_same_midrank_without_random_bonus(self):
        reference = [0] * 10 + [1] * 10
        value = profile_fraction(0, reference, "모임형", "rank_direction")
        self.assertEqual(value["quantile"], 0.25)
        self.assertEqual(value["profile_fraction"], 0.25)

    def test_direction_differs_by_agglomeration_profile(self):
        reference = list(range(20))
        meeting = profile_fraction(15, reference, "모임형", "rank_direction")
        nearby = profile_fraction(15, reference, "근처형", "rank_direction")
        self.assertAlmostEqual(meeting["profile_fraction"] + nearby["profile_fraction"], 1)

    def test_hump_favors_middle_rank_and_keeps_both_extremes_low(self):
        reference = list(range(21))
        middle = profile_fraction(10, reference, "근처형", "rank_hump_near")
        low = profile_fraction(0, reference, "근처형", "rank_hump_near")
        high = profile_fraction(20, reference, "근처형", "rank_hump_near")
        self.assertEqual(middle["profile_fraction"], 1)
        self.assertAlmostEqual(low["profile_fraction"], high["profile_fraction"])
        self.assertLess(low["profile_fraction"], 0.1)

    def test_hump_does_not_change_meeting_profile_direction(self):
        reference = list(range(20))
        a = profile_fraction(15, reference, "모임형", "rank_direction")
        b = profile_fraction(15, reference, "모임형", "rank_hump_near")
        self.assertEqual(a, b)

    def test_missing_or_unsorted_reference_is_not_replaced_with_neutral_points(self):
        for reference in ([0] * 19, list(range(20))[::-1], [None] * 20, [-1] * 20):
            with self.assertRaises(ValueError):
                profile_fraction(1, reference, "근처형", "rank_direction")


if __name__ == "__main__":
    unittest.main()
