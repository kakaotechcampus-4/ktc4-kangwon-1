"""연속화가 기존 경계 주변의 점프만 줄이고 결측을 채우지 않는지 확인합니다."""

import copy
import unittest

from backtest.rank_d_smooth import RATIO_EDGES, demand_adjustment, smooth_grade


class SmoothDemandTests(unittest.TestCase):
    def test_continuity_monotonicity_and_bounded_grade(self):
        values = [smooth_grade(i / 1000, RATIO_EDGES) for i in range(2001)]
        self.assertEqual(values, sorted(values))
        self.assertEqual((min(values), max(values)), (0, 4))
        for edge in RATIO_EDGES:
            self.assertLess(
                abs(
                    smooth_grade(edge - 1e-8, RATIO_EDGES) - smooth_grade(edge + 1e-8, RATIO_EDGES)
                ),
                1e-6,
            )

    def test_boundary_grade_is_midpoint_between_original_steps(self):
        for i, edge in enumerate(RATIO_EDGES):
            self.assertEqual(smooth_grade(edge, RATIO_EDGES), i + 0.5)

    def test_D1_retains_weakest_component_rule_and_original_inputs(self):
        items = {
            "D1": {"status": "observed", "grade": 0, "points": 0, "value": {"r": 0.75, "p": 95}},
            "D2": {"status": "unknown"},
            "D3": {"status": "n.a."},
            "D4": {"status": "unknown"},
        }
        original = copy.deepcopy(items)
        result = demand_adjustment(items, "all", 35)
        self.assertAlmostEqual(result["items"]["D1"]["new_grade"], 1 / 6)
        self.assertEqual(items, original)
        self.assertEqual(set(result["items"]), {"D1"})

    def test_unknown_unapplied_and_scalar_D1_remain_unchanged(self):
        items = {
            "D1": {"status": "observed", "value": 100},
            "D2": {"status": "unknown"},
            "D3": {"status": "n.a."},
            "D4": {"status": "unknown"},
        }
        self.assertEqual(demand_adjustment(items, "all", 35)["weighted_delta"], 0)

    def test_reconstructed_original_grade_is_required(self):
        items = {
            "D2": {"status": "observed", "value": 1, "grade": 4, "points": 10},
            "D3": {"status": "n.a."},
            "D4": {"status": "unknown"},
        }
        with self.assertRaises(ValueError):
            demand_adjustment(items, "secondary", 35)


if __name__ == "__main__":
    unittest.main()
