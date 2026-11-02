"""행 누락을 실제0과 구분하고 같은 원천만 비교하는지 검증합니다."""

import copy
import unittest

from app.agents.business_lifecycle.client import get_recent_quarters
from app.industries.catalog import INDUSTRY_TO_SEOUL
from backtest.source_provenance import counts, evidence, replace_contributions, totals


class SourceProvenanceTests(unittest.TestCase):
    def test_archived_CSV_numeric_strings_are_validated_without_zero_fill(self):
        row = {"SIMILR_INDUTY_STOR_CO": "12", "OPBIZ_STOR_CO": "0.0", "CLSBIZ_STOR_CO": None}
        self.assertEqual(counts(row), (12, 0, None))
        for value in ("", "NaN", "-1", "1.5", True):
            with self.assertRaises(ValueError):
                counts({**row, "SIMILR_INDUTY_STOR_CO": value})

    def inputs(self):
        quarters = get_recent_quarters("20252", 12)
        sources = INDUSTRY_TO_SEOUL["I210"]
        local = {q: {s: (10, 2, 0) for s in sources} for q in quarters}
        city = {q: {s: (100, 20, 10) for s in sources} for q in quarters}
        return quarters, sources, local, city

    def test_explicit_zero_stays_observed_but_absent_row_is_partial(self):
        q, s, local, city = self.inputs()
        self.assertEqual(
            counts({"SIMILR_INDUTY_STOR_CO": 0, "OPBIZ_STOR_CO": 0, "CLSBIZ_STOR_CO": 0}), (0, 0, 0)
        )
        self.assertFalse(evidence("I210", q, local, city)["items"]["S1"]["partial"])
        del local[q[-1]][s[0]]
        self.assertTrue(evidence("I210", q, local, city)["items"]["S1"]["partial"])
        with self.assertRaises(ValueError):
            totals(local, q, tuple(s))

    def test_only_required_windows_are_marked_partial(self):
        q, s, local, city = self.inputs()
        del local[q[5]][s[0]]
        found = evidence("I210", q, local, city)["items"]
        self.assertFalse(found["S1"]["partial"])
        self.assertFalse(found["S4"]["partial"])
        self.assertTrue(found["S2"]["partial"])
        self.assertTrue(found["S3"]["partial"])

    def test_matching_subset_and_city_share_do_not_invent_missing_components(self):
        q, s, local, city = self.inputs()
        for quarter in q:
            del local[quarter][s[0]]
        original = copy.deepcopy((local, city))
        value = evidence("I210", q, local, city)["items"]["S1"]
        self.assertNotIn(s[0], value["common_sources"])
        self.assertEqual(value["estimate"]["local_counts"][2], 0)
        self.assertEqual(value["estimate"]["grade"], 4)
        self.assertAlmostEqual(value["estimate"]["city_exposure_share"], (len(s) - 1) / len(s))
        self.assertEqual((local, city), original)

    def test_empty_subset_unsupported_and_invalid_counts_are_not_real_zero(self):
        q, s, local, city = self.inputs()
        value = evidence("I210", q, {}, city)
        self.assertFalse(value["items"]["S1"]["estimate"]["available"])
        self.assertFalse(evidence("I207", q, local, city)["supported"])
        local[q[-1]][s[0]] = (None, 0, 0)
        self.assertTrue(evidence("I210", q, local, city)["items"]["S1"]["invalid_count_rows"])

    def test_partial_estimate_keeps_unknown_weight_and_source_status(self):
        q, s, local, city = self.inputs()
        for quarter in q:
            del local[quarter][s[0]]
        ev = evidence("I210", q, local, city)
        trace = {
            "status": {n: "unknown" for n in ("S1", "S2", "S3", "S4")},
            "observed": {n: None for n in ("S1", "S2", "S3", "S4")},
            "estimated_S": {},
        }
        original = copy.deepcopy(trace)
        result = replace_contributions(trace, ev, "matched_city_share")
        self.assertGreater(result["items"]["S1"]["new_weighted_points"], 0)
        self.assertLess(result["items"]["S1"]["new_weighted_points"], 5)
        self.assertEqual(trace, original)
        self.assertTrue(result["items"]["S1"]["unknown_applicable_weight_kept"])

    def test_full_provenance_points_and_invalid_trend_denominator_are_preserved(self):
        q, s, local, city = self.inputs()
        ev = evidence("I210", q, local, city)
        trace = {
            "status": {n: "observed" for n in ("S1", "S2", "S3", "S4")},
            "observed": {n: 7.5 for n in ("S1", "S2", "S3", "S4")},
            "estimated_S": {},
        }
        self.assertEqual(replace_contributions(trace, ev, "withhold_partial")["weighted_delta"], 0)
        for quarter in q:
            del local[quarter][s[0]]
        self.assertFalse(evidence("I210", q, local, city)["items"]["S4"]["estimate"]["available"])


if __name__ == "__main__":
    unittest.main()
