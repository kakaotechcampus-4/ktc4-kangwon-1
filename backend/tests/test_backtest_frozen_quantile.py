"""새 위치용 고정 후보가 관측·정책·희소 추정을 같은 배점으로 재현하는지 확인합니다."""

import copy
import unittest

from backtest.frozen_quantile import ITEM_WEIGHTS, fractions_for


class FrozenQuantileTests(unittest.TestCase):
    def source(self):
        trace = {
            "observed": {
                name: (
                    7.5
                    if name.startswith("S")
                    else 7.5
                    if name == "C1"
                    else 5
                    if name != "D4"
                    else 2.5
                )
                for name in ITEM_WEIGHTS
            },
            "status": {name: "observed" for name in ITEM_WEIGHTS},
            "D_adjustment": {"items": {}},
            "C1_policy": {"applied": False},
            "estimated_S": {},
        }
        row = {
            "items": {
                "C1": {"status": "observed", "value": 1, "grade": 2, "agglomeration": "모임형"}
            }
        }
        return row, trace, {"count": 10, "lq": 1}, list(range(20))

    def test_group_weights_keep80_and15_for_S(self):
        self.assertEqual(sum(ITEM_WEIGHTS.values()), 80)
        self.assertEqual(sum(v for k, v in ITEM_WEIGHTS.items() if k.startswith("S")), 15)

    def test_D75_adjustment_changes_only_its_original_fraction(self):
        row, trace, commercial, reference = self.source()
        trace["D_adjustment"]["items"]["D1"] = {"weighted_delta": 2}
        value = fractions_for(row, trace, commercial, reference)
        self.assertAlmostEqual(value["D1"], 0.65)
        self.assertEqual(value["D2"], 0.5)

    def test_fixed_C1_policy_retains_separate_reference_delta(self):
        row, trace, commercial, reference = self.source()
        row["items"]["C1"]["value"] = None
        trace["C1_policy"] = {"applied": True, "mode": "lq_shrink5", "weighted_point_delta": 2.5}
        self.assertAlmostEqual(fractions_for(row, trace, commercial, reference)["C1"], 0.6)

    def test_unknown_C1_is_not_filled_by_positive_counts(self):
        row, trace, commercial, reference = self.source()
        row["items"]["C1"]["status"] = "unknown"
        trace["status"]["C1"], trace["observed"]["C1"] = "unknown", None
        self.assertEqual(fractions_for(row, trace, commercial, reference)["C1"], 0)

    def test_unknown_S_estimate_remains_separate_and_unsupported_remains0(self):
        row, trace, commercial, reference = self.source()
        for name in ("S1", "S2"):
            trace["status"][name], trace["observed"][name] = "unknown", None
        trace["estimated_S"]["S1"] = 0.75
        original = copy.deepcopy(trace)
        value = fractions_for(row, trace, commercial, reference)
        self.assertEqual(value["S1"], 0.1)
        self.assertEqual(value["S2"], 0)
        self.assertEqual(trace, original)

    def test_undefined_LQ_keeps_existing_C1_fraction(self):
        row, trace, commercial, reference = self.source()
        commercial["lq"] = None
        self.assertEqual(fractions_for(row, trace, commercial, reference)["C1"], 0.5)


if __name__ == "__main__":
    unittest.main()
