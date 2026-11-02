"""90점의 실제 배점·미적용·결측·검증된 S4 보완을 확인합니다."""

import copy
import unittest

from backtest.score90 import CONFIGURATIONS, Score90Configuration, score90


class Score90Tests(unittest.TestCase):
    def inputs(self):
        fractions = {n: 0.5 for n in CONFIGURATIONS[0].weights}
        statuses = {n: "observed" for n in fractions}
        profile = {"required_facilities": "SC4", "required_facilities_confidence": "low"}
        components = {"SC4": {"status": "observed", "points": 10}}
        return fractions, statuses, profile, components

    def test_all_configurations_have_80_plus_actual_10_not_85_rescaled(self):
        for config in CONFIGURATIONS:
            with self.subTest(config=config.name):
                self.assertAlmostEqual(sum(config.weights.values()), 80)
                result = score90(*self.inputs(), config)
                self.assertEqual(result["effective_C4_weight"], 10)
                self.assertAlmostEqual(result["applicable_weight"], 90)
                self.assertAlmostEqual(result["normalized"], 50)

    def test_unknown_S_stays_in_denominator_with_zero_contribution(self):
        f, s, p, c = self.inputs()
        for name in ("S1", "S2", "S3", "S4"):
            f[name] = 0
            s[name] = "unknown"
        result = score90(f, s, p, c, Score90Configuration(30, "equal"))
        self.assertEqual(result["S_points"], 0)
        self.assertEqual(result["applicable_weight"], 90)
        self.assertEqual(result["source_status"]["S4"], "unknown")

    def test_non_applicable_items_exclude_weight_instead_of_becoming_observed_zero(self):
        f, s, p, c = self.inputs()
        f["D1"] = 0
        s["D1"] = "n.a."
        p = {"required_facilities": ""}
        c = {}
        result = score90(f, s, p, c, Score90Configuration(30, "equal"))
        self.assertEqual(result["common80_applicable"], 70)
        self.assertEqual(result["effective_C4_weight"], 0)
        self.assertAlmostEqual(result["normalized"], 45)

    def test_separate_S4_repair_does_not_change_source_status_or_input(self):
        f, s, p, c = self.inputs()
        f["S4"] = 0
        s["S4"] = "unknown"
        before = copy.deepcopy((f, s, p, c))
        config = Score90Configuration(30, "recent", True)
        result = score90(f, s, p, c, config, S4_repair=0.5)
        self.assertTrue(result["S4_separate_repair_applied"])
        self.assertEqual(result["source_status"]["S4"], "unknown")
        self.assertEqual((f, s, p, c), before)

    def test_unavailable_repair_does_not_fill_S4(self):
        f, s, p, c = self.inputs()
        f["S4"] = 0
        s["S4"] = "unknown"
        result = score90(f, s, p, c, Score90Configuration(30, "equal", True))
        self.assertFalse(result["S4_separate_repair_applied"])
        self.assertEqual(result["item_contributions"]["S4"], 0)

    def test_verified_S4_repair_cannot_overwrite_an_observation(self):
        with self.assertRaises(ValueError):
            score90(*self.inputs(), Score90Configuration(30, "equal", True), S4_repair=0.5)

    def test_unknown_facility_keeps_actual_ten_weight_and_separate_policy_credit(self):
        f, s, p, c = self.inputs()
        c["SC4"] = {"status": "unknown", "points": None}
        result = score90(f, s, p, c, Score90Configuration(30, "equal"))
        self.assertEqual(result["effective_C4_weight"], 10)
        self.assertEqual(result["C4_source_status"], "unknown")
        self.assertIsNone(result["observed_aggregate_points"])
        self.assertEqual(result["normalized"], 42.5)
        self.assertLess(result["normalized"], 45)

    def test_growth_and_stability_weights_are_explicit_and_positive(self):
        stable = Score90Configuration(30, "stable").weights
        growth = Score90Configuration(30, "growth").weights
        self.assertGreater(stable["S1"], stable["S2"])
        self.assertGreater(stable["S3"], stable["S4"])
        self.assertGreater(growth["S2"], growth["S1"])

    def test_invalid_observation_or_nonfinite_fraction_is_rejected(self):
        for fraction in [float("nan"), 2, -1]:
            f, s, p, c = self.inputs()
            f["S1"] = fraction
            with self.assertRaises(ValueError):
                score90(f, s, p, c, Score90Configuration(30, "equal"))
        f, s, p, c = self.inputs()
        s["D1"] = "n.a."
        with self.assertRaises(ValueError):
            score90(f, s, p, c, Score90Configuration(30, "equal"))


if __name__ == "__main__":
    unittest.main()
