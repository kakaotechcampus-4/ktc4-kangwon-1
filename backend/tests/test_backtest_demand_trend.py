"""분기 일수·같은 상권·실제0·결측·주변 분포의 교차표 오인을 검증합니다."""

import copy
import unittest
from types import SimpleNamespace

from backtest.demand_trend import d4_fraction, observed_change, replacement, segment_changes


class DemandTrendTests(unittest.TestCase):
    def panels(self):
        return {
            "20242": {
                "a": SimpleNamespace(
                    total=1000, by_age={"20": 100, "30": 200}, by_time={"17_21": 100}
                )
            },
            "20252": {
                "a": SimpleNamespace(
                    total=1100, by_age={"20": 200, "30": 100}, by_time={"17_21": 200}
                )
            },
        }

    def test_total_can_grow_while_customer_age_segment_does_not(self):
        p = self.panels()
        profile = {
            "primary_bands": "17_21",
            "target_age_bands": "20;30",
            "target_population": "상주",
        }
        value = segment_changes(profile, ["a"], p)
        self.assertAlmostEqual(value["total"]["yoy"], 0.1, places=4)
        self.assertEqual(value["age"]["yoy"], 0)
        self.assertTrue(value["age_is_floating_proxy_for_D3_population"])

    def test_missing_year_or_changed_area_set_is_not_filled_with_zero(self):
        p = self.panels()
        p["20242"] = {}
        self.assertFalse(observed_change(["a"], p, "total")["available"])

    def test_missing_age_is_distinct_from_actual_zero(self):
        p = self.panels()
        p["20252"]["a"].by_age["20"] = 0
        value = observed_change(["a"], p, "by_age", ["20"])
        self.assertTrue(value["available"])
        self.assertEqual(value["yoy"], -1)
        p["20252"]["a"].by_age["20"] = None
        self.assertFalse(observed_change(["a"], p, "by_age", ["20"])["available"])

    def test_zero_old_denominator_is_unknown_instead_of_unbounded_growth(self):
        p = self.panels()
        p["20242"]["a"].by_age["20"] = 0
        self.assertFalse(observed_change(["a"], p, "by_age", ["20"])["available"])

    def test_combination_averages_measured_marginal_changes_without_joint_counts(self):
        evidence = {"time": {"available": True, "yoy": 0.2}, "age": {"available": True, "yoy": 0}}
        original = copy.deepcopy(evidence)
        value = replacement(evidence, "mean_marginal_yoy")
        self.assertEqual(value["change"], 0.1)
        self.assertTrue(value["does_not_infer_joint_age_time_counts"])
        self.assertEqual(evidence, original)

    def test_D4_curve_is_bounded_and_increasing(self):
        values = [d4_fraction(v) for v in [-1, -0.1, -0.03, 0, 0.03, 0.1, 1]]
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[0], 0)
        self.assertEqual(values[-1], 1)


if __name__ == "__main__":
    unittest.main()
