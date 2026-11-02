"""실제0건·누락·희소 관측을 S4에서 다르게 취급하는지 확인합니다."""

import copy
import unittest

from app.agents.business_lifecycle.client import get_recent_quarters
from app.industries.catalog import INDUSTRY_TO_SEOUL
from backtest.s4_difference import changed_fraction, difference_evidence


class S4DifferenceTests(unittest.TestCase):
    def source(self, *, exposure=10, old_closed=0, new_closed=0):
        quarters = get_recent_quarters("20252", 12)
        code = "M111"
        sources = INDUSTRY_TO_SEOUL[code]
        local = {
            q: {s: (exposure, 0, old_closed if i < 4 else new_closed) for s in sources}
            for i, q in enumerate(quarters)
        }
        city = {q: {s: (100, 5, 5) for s in sources} for q in quarters}
        return code, quarters, local, city

    def test_actual_zero_old_closures_gives_finite_neutral_change(self):
        args = self.source()
        before = copy.deepcopy(args)
        evidence = difference_evidence(*args)
        self.assertTrue(evidence["available"])
        self.assertEqual(evidence["fraction"], 0.5)
        self.assertEqual(changed_fraction("unknown", evidence, "zero_old_only"), 0.5)
        self.assertEqual(args, before)

    def test_missing_row_is_not_observed_zero(self):
        code, quarters, local, city = self.source()
        del local[quarters[0]][INDUSTRY_TO_SEOUL[code][0]]
        evidence = difference_evidence(code, quarters, local, city)
        self.assertFalse(evidence["available"])
        self.assertIsNone(changed_fraction("unknown", evidence, "rate_difference_complete"))

    def test_more_recent_closures_lower_fraction(self):
        stable = difference_evidence(*self.source(new_closed=0))
        worsening = difference_evidence(*self.source(new_closed=2))
        self.assertLess(worsening["fraction"], stable["fraction"])

    def test_less_exposure_keeps_quadratic_disadvantage(self):
        full = difference_evidence(*self.source(exposure=10))
        sparse = difference_evidence(*self.source(exposure=5))
        self.assertEqual(sparse["fraction"], full["fraction"] / 4)
        self.assertIsNone(changed_fraction("unknown", sparse, "zero_old_only"))
        self.assertEqual(
            changed_fraction("unknown", sparse, "rate_difference_complete"), sparse["fraction"]
        )

    def test_unsupported_or_zero_exposure_stays_unavailable(self):
        _, quarters, local, city = self.source()
        self.assertFalse(difference_evidence("I207", quarters, local, city)["available"])
        self.assertFalse(difference_evidence(*self.source(exposure=0))["available"])

    def test_only_required_windows_need_actual_rows_and_policy_keeps_observed(self):
        code, quarters, local, city = self.source()
        del local[quarters[5]]
        evidence = difference_evidence(code, quarters, local, city)
        self.assertTrue(evidence["available"])
        self.assertIsNone(changed_fraction("observed", evidence, "zero_old_only"))
        self.assertIsNone(changed_fraction("unknown", evidence, "control"))
        self.assertIsNone(changed_fraction("n.a.", evidence, "rate_difference_complete"))


if __name__ == "__main__":
    unittest.main()
