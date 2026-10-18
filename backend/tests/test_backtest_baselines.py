import unittest

from app.agentic import scoring
from app.agents.business_lifecycle import baseline as lifecycle
from app.agents.commercial_area import baseline as density
from app.agents.floating_population import baseline as floating
from backtest.baselines import BaselineMismatch, swapped
from tests.backtest_fixture import file_values


class SwapTests(unittest.TestCase):
    def setUp(self):
        self.quarter = scoring.BASELINE_BASE_QUARTER
        self.lifecycle = lifecycle.SEOUL_INDUSTRY_LIFECYCLE_BASELINE
        self.density = density.SEOUL_INDUSTRY_DENSITY_PERCENTILES
        self.daily = floating.DAILY_TOTAL_PERCENTILES

    def assert_restored(self):
        self.assertEqual(scoring.BASELINE_BASE_QUARTER, self.quarter)
        self.assertIs(lifecycle.SEOUL_INDUSTRY_LIFECYCLE_BASELINE, self.lifecycle)
        self.assertIs(scoring.SEOUL_INDUSTRY_DENSITY_PERCENTILES, self.density)
        self.assertIs(density.SEOUL_INDUSTRY_DENSITY_PERCENTILES, self.density)
        self.assertIs(floating.DAILY_TOTAL_PERCENTILES, self.daily)

    def test_swaps_with_original_key_types_and_restores(self):
        values = file_values()
        doubled = {k: v * 2 for k, v in values["floating"]["DAILY_TOTAL_PERCENTILES"].items()}
        values["floating"]["DAILY_TOTAL_PERCENTILES"] = doubled
        probe = self.daily[50]
        outside = floating.daily_total_percentile(probe)
        with swapped(values):
            self.assertEqual(scoring.BASELINE_BASE_QUARTER, "20234")
            self.assertEqual(lifecycle.BASELINE_BASE_QUARTER, "20234")
            self.assertEqual(set(floating.DAILY_TOTAL_PERCENTILES), set(self.daily))
            first = next(iter(scoring.SEOUL_INDUSTRY_DENSITY_PERCENTILES.values()))
            self.assertTrue(all(type(key) is int for key in first))
            self.assertLess(floating.daily_total_percentile(probe), outside)
        self.assert_restored()

    def test_restores_after_an_error(self):
        with self.assertRaises(RuntimeError), swapped(file_values()):
            raise RuntimeError("중간 오류")
        self.assert_restored()

    def test_missing_section_stops_before_any_swap(self):
        values = file_values()
        del values["density"]
        with self.assertRaises(BaselineMismatch), swapped(values):
            pass
        self.assert_restored()

    def test_unknown_industry_is_rejected(self):
        values = file_values()
        values["lifecycle"]["X999"] = next(iter(values["lifecycle"].values()))
        with self.assertRaises(BaselineMismatch), swapped(values):
            pass

    def test_missing_age_band_is_rejected(self):
        values = file_values()
        ages = values["floating"]["AGE_SHARE_AVG"]
        ages.pop(next(iter(ages)))
        with self.assertRaises(BaselineMismatch), swapped(values):
            pass

    def test_text_in_place_of_a_number_is_rejected(self):
        values = file_values()
        values["floating"]["WEEKEND_TO_WEEKDAY_AVG"] = "0.97"
        with self.assertRaises(BaselineMismatch), swapped(values):
            pass

    def test_industry_missing_in_the_past_is_allowed(self):
        values = file_values()
        gone = next(iter(values["lifecycle"]))
        del values["lifecycle"][gone]
        with swapped(values):
            self.assertNotIn(gone, scoring.SEOUL_INDUSTRY_LIFECYCLE_BASELINE)
        self.assert_restored()

    def test_industry_missing_in_density_is_rejected(self):
        values = file_values()
        gone = next(iter(values["density"]))
        del values["density"][gone]
        with self.assertRaises(BaselineMismatch), swapped(values):
            pass
        self.assert_restored()

    def test_label_follows_the_baseline_quarter_and_is_restored(self):
        original = floating.BASELINE_LABEL
        with swapped(file_values()):
            self.assertIn("2023년 4분기", floating.BASELINE_LABEL)
            self.assertNotIn("2026", floating.BASELINE_LABEL)
            self.assertNotIn("1,648", floating.BASELINE_LABEL)
        self.assertEqual(floating.BASELINE_LABEL, original)


if __name__ == "__main__":
    unittest.main()
