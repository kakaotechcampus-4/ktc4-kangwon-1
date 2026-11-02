"""경쟁·수요의 결합 경계와 유형별 적용 범위를 확인합니다."""

import unittest

from backtest.c1_combination import MODES, combine


class CompetitionCombinationTests(unittest.TestCase):
    def test_control_and_weighted_fraction_are_known_values(self):
        self.assertEqual(combine(0.75, 1, "근처형", "low", "control")["fraction"], 0.625)
        self.assertEqual(combine(0.75, 1, "근처형", "low", "all_LQ75")["fraction"], 0.5625)

    def test_geometric_and_harmonic_require_both_signals(self):
        for mode in ("geometric", "harmonic"):
            self.assertEqual(combine(0.9, 0, "근처형", "low", mode)["fraction"], 0)
            self.assertEqual(combine(0, 5, "모임형", "low", mode)["fraction"], 0)
            self.assertEqual(combine(0, 0, "모임형", "low", mode)["fraction"], 0)

    def test_scope_does_not_reweight_unrelated_profiles(self):
        original = combine(0.8, 1, "모임형", "high", "control")["fraction"]
        self.assertEqual(combine(0.8, 1, "모임형", "high", "near_LQ75")["fraction"], original)
        self.assertEqual(
            combine(0.8, 1, "모임형", "high", "low_confidence_LQ75")["fraction"], original
        )

    def test_all_modes_stay_in_budget(self):
        for mode in MODES:
            for p in (0, 0.2, 0.5, 1):
                for lq in (0, 0.01, 1, 50):
                    value = combine(p, lq, "근처형", "low", mode)["fraction"]
                    self.assertGreaterEqual(value, 0)
                    self.assertLessEqual(value, 1)

    def test_invalid_measurement_cannot_become_zero(self):
        for p, lq in (
            (None, 1),
            (0.5, None),
            (True, 1),
            (0.5, -1),
            (float("nan"), 1),
            (0.5, float("inf")),
        ):
            with self.subTest(p=p, lq=lq), self.assertRaises(ValueError):
                combine(p, lq, "근처형", "low", "control")
