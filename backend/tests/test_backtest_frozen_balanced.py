"""새 위치용 균형 후보가 상태·미적용·원천누락을 보존하는지 확인합니다."""

import copy
import unittest

from app.agents.business_lifecycle.client import get_recent_quarters
from app.industries.catalog import INDUSTRY_TO_SEOUL
from backtest.frozen_balanced import components_for


class FrozenBalancedTests(unittest.TestCase):
    def trace(self):
        return {
            "observed": {
                "D1": 5,
                "D2": 5,
                "D3": 5,
                "D4": 2.5,
                "C1": 7.5,
                "S1": 3.75,
                "S2": 3.75,
                "S3": 3.75,
                "S4": None,
            },
            "status": {
                name: "unknown" if name == "S4" else "observed"
                for name in ("D1", "D2", "D3", "D4", "C1", "S1", "S2", "S3", "S4")
            },
            "estimated_S": {},
            "D_adjustment": {"weighted_delta": 0},
            "C1_policy": {"applied": False},
        }

    def test_actual_zero_repairs_only_S4_and_keeps_original_unknown(self):
        code = "M111"
        source = INDUSTRY_TO_SEOUL[code][0]
        quarters = get_recent_quarters("20252", 12)
        local = {q: {source: [10, 0, 0]} for q in quarters}
        city = {q: {source: [100, 5, 5]} for q in quarters}
        trace = self.trace()
        before = copy.deepcopy(trace)
        value = components_for(code, trace, local, city, partial=False)
        self.assertEqual(value["S_fractions"]["S4"], 0.5)
        self.assertEqual(value["source_status"]["S4"], "unknown")
        self.assertEqual(value["D_points"], 17.5)
        self.assertEqual(trace, before)

    def test_missing_or_partial_source_does_not_make_S4_points(self):
        trace = self.trace()
        for partial in (True, False):
            value = components_for("M111", trace, {}, {}, partial=partial)
            self.assertEqual(value["S_fractions"]["S4"], 0)
            self.assertIsNone(value["S4_derived_repair"])

    def test_NA_D_and_fixed_C1_policy_are_not_new_observations(self):
        trace = self.trace()
        trace["status"]["D2"] = "n.a."
        trace["observed"]["D2"] = None
        trace["C1_policy"] = {"applied": True, "mode": "lq_shrink5", "weighted_point_delta": 2.5}
        value = components_for("M111", trace, {}, {}, partial=False)
        self.assertEqual(value["D_applicable"], 25)
        self.assertAlmostEqual(value["C1_fraction"], 0.6)
        self.assertTrue(value["C1_policy_is_not_measured_customer_fit"])


if __name__ == "__main__":
    unittest.main()
