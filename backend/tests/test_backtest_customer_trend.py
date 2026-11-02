"""상주·직장 인원수와 유동 통행량의 단위·분모·관측 집합을 검증합니다."""

import unittest
from types import SimpleNamespace

from backtest.customer_trend import age_change, evidence_for, relative_change


class CustomerTrendTests(unittest.TestCase):
    def panel(self):
        return {
            "20242": {"a": SimpleNamespace(by_age={"20": 100})},
            "20252": {"a": SimpleNamespace(by_age={"20": 110})},
        }

    def test_resident_stock_is_not_divided_by_quarter_days(self):
        r = age_change(["a"], self.panel(), ["20"], flow=False)
        self.assertEqual(r["levels"], {"20242": 100, "20252": 110})
        self.assertEqual(r["yoy"], 0.1)
        self.assertEqual(r["unit"], "persons_stock")

    def test_floating_is_explicitly_a_daily_flow(self):
        r = age_change(["a"], self.panel(), ["20"], flow=True)
        self.assertEqual(r["unit"], "persons_per_day")
        self.assertEqual(r["levels"]["20242"], round(100 / 91, 1))

    def test_changed_coverage_or_missing_age_cannot_become_growth(self):
        p = self.panel()
        p["20242"] = {}
        self.assertFalse(age_change(["a"], p, ["20"], flow=False)["available"])
        p = self.panel()
        p["20252"]["a"].by_age["20"] = None
        self.assertFalse(age_change(["a"], p, ["20"], flow=False)["available"])

    def test_true_zero_is_observed_decline_but_old_zero_is_uncomputable(self):
        p = self.panel()
        p["20252"]["a"].by_age["20"] = 0
        self.assertEqual(age_change(["a"], p, ["20"], flow=False)["yoy"], -1)
        p = self.panel()
        p["20242"]["a"].by_age["20"] = 0
        self.assertFalse(age_change(["a"], p, ["20"], flow=False)["available"])

    def test_population_does_not_fallback_to_a_different_kind(self):
        r = evidence_for(
            {"target_population": "상주", "target_age_bands": "20"},
            ["a"],
            {"유동": self.panel()},
            {},
        )
        self.assertFalse(r["available"])

    def test_city_growth_reference_uses_matching_population_and_explicit_common_areas(self):
        panel = self.panel()
        panel["20252"]["new"] = SimpleNamespace(by_age={"20": 999})
        r = evidence_for(
            {"target_population": "상주", "target_age_bands": "20"}, ["a"], {"상주": panel}, {}
        )
        self.assertEqual(
            r["city_matched_area_reference"]["excluded_nonmatching_city_areas"], ["new"]
        )
        self.assertFalse(r["proxy_population_used"])
        self.assertAlmostEqual(relative_change(r), 0)


if __name__ == "__main__":
    unittest.main()
