"""정책 고정값만 시험하고 실제 관측·미확인 점수를 바꾸지 않는지 확인합니다."""

import copy
import unittest

from backtest.rank_c1_policy import apply_policy


class C1PolicyTests(unittest.TestCase):
    def inputs(self, count=10, lq=3):
        base = {"observed_points": 25, "estimated_points": 2, "normalized": 27, "applicable": 80}
        item = {
            "status": "observed",
            "agglomeration": "무관",
            "value": None,
            "points": 7.5,
            "grade": 2,
        }
        data = {
            "commercial_collection_complete": True,
            "comparison_radius_m": 2000,
            "commercial_area": {
                "radius_m": 500,
                "by_middle": [{"code": "M103", "count": count, "lq": lq}],
            },
        }
        return base, item, data

    def test_measured_unknown_and_unapplied_items_cannot_be_changed(self):
        base, item, data = self.inputs()
        for modified in (
            {**item, "value": 1, "agglomeration": "근처형"},
            {**item, "status": "unknown"},
            {**item, "status": "n.a."},
        ):
            result = apply_policy(base, modified, "M103", data, 15, "lq_shrink5")
            self.assertEqual(result["normalized"], base["normalized"])
            self.assertFalse(result["policy_change"]["applied"])

    def test_policy_exclusion_removes_only_C1_and_keeps_other_unknown_weight(self):
        base, item, data = self.inputs()
        result = apply_policy(base, item, "M103", data, 15, "not_applicable")
        self.assertEqual(result["policy_adjusted_applicable"], 65)
        self.assertAlmostEqual(result["normalized"], 80 * (27 - 7.5) / 65)
        self.assertEqual(result["estimated_points"], base["estimated_points"])
        self.assertEqual(result["observed_points"], base["observed_points"])

    def test_zero_count_keeps_policy_midpoint_and_less_data_gives_less_adjustment(self):
        changes = []
        for count in (0, 1, 10):
            base, item, data = self.inputs(count=count)
            result = apply_policy(base, item, "M103", data, 15, "lq_shrink5")
            changes.append(result["policy_change"]["weighted_point_delta"])
        self.assertEqual(changes[0], 0)
        self.assertEqual(changes, sorted(changes))
        self.assertLess(changes[-1], 15 / 4)

    def test_low_LQ_can_lower_estimate_and_conservative_prior_changes_less(self):
        base, item, data = self.inputs(lq=0.2)
        original = copy.deepcopy((base, item, data))
        a = apply_policy(base, item, "M103", data, 25, "lq_shrink5")
        b = apply_policy(base, item, "M103", data, 25, "lq_shrink10")
        self.assertLess(a["normalized"], b["normalized"])
        self.assertLess(b["normalized"], base["normalized"])
        self.assertEqual((base, item, data), original)

    def test_partial_market_and_wrong_radius_do_not_create_new_evidence(self):
        base, item, data = self.inputs()
        for modified in (
            {**data, "commercial_collection_complete": False},
            {**data, "comparison_radius_m": 1000},
            {**data, "commercial_split_missing": ["M103"]},
        ):
            result = apply_policy(base, item, "M103", modified, 15, "lq_shrink5")
            self.assertFalse(result["policy_change"]["applied"])
            self.assertEqual(result["normalized"], base["normalized"])

    def test_missing_comparison_LQ_is_not_treated_as_observed_zero(self):
        base, item, data = self.inputs(lq=None)
        result = apply_policy(base, item, "M103", data, 15, "lq_shrink5")
        self.assertFalse(result["policy_change"]["applied"])
        self.assertEqual(result["normalized"], base["normalized"])


if __name__ == "__main__":
    unittest.main()
