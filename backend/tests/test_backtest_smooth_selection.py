"""연속화 선택에서 원래 점수·학습 범위·추천 분포 제약이 유지되는지 확인합니다."""

import copy
import math
import unittest

from backtest.smooth_selection import FRACTIONS, blend_scores, select_fraction


class SmoothSelectionTests(unittest.TestCase):
    def test_endpoints_and_blend_preserve_inputs_and_score_scale(self):
        base, continuous = {"A": 20.0, "B": 60.0}, {"A": 40.0, "B": 50.0}
        original = copy.deepcopy((base, continuous))
        self.assertEqual(blend_scores(base, continuous, 0), base)
        self.assertEqual(blend_scores(base, continuous, 1), continuous)
        self.assertEqual(blend_scores(base, continuous, 0.5), {"A": 30.0, "B": 55.0})
        self.assertEqual((base, continuous), original)

    def test_unplanned_weight_missing_candidate_and_invalid_score_are_rejected(self):
        for base, end, weight in (
            ({"A": 1}, {"A": 2}, 0.1),
            ({"A": 1}, {"B": 2}, 0.5),
            ({"A": math.nan}, {"A": 2}, 0.5),
        ):
            with self.assertRaises(ValueError):
                blend_scores(base, end, weight)

    def setup_selection(self):
        training = [
            {"id": "a", "target": "0", "cluster": "one"},
            {"id": "b", "target": "11", "cluster": "two"},
        ]
        codes = [str(i) for i in range(12)]
        predictions = {
            c["id"]: {m: {v: 12 - i for i, v in enumerate(codes)} for m in FRACTIONS}
            for c in training
        }
        orders = {c["id"]: {m: codes[:] for m in FRACTIONS} for c in training}
        for m in FRACTIONS:
            orders["b"][m] = list(reversed(codes))
            predictions["b"][m] = {v: i for i, v in enumerate(codes)}
        return training, predictions, orders

    def test_held_cases_cannot_change_selection(self):
        training, predictions, orders = self.setup_selection()
        expected = select_fraction(training, predictions, orders)
        predictions["held"] = {"only_held": {"A": 999}}
        orders["held"] = {"only_held": ["A"]}
        self.assertEqual(expected, select_fraction(training, predictions, orders))
        self.assertEqual(expected["method"], "d_0")

    def test_better_target_loss_cannot_bypass_concentration_constraint(self):
        training, predictions, orders = self.setup_selection()
        training[1]["target"] = "0"
        for c in training:
            predictions[c["id"]]["d_100"]["0"] = 80
            orders[c["id"]]["d_100"] = ["0", *[v for v in orders[c["id"]]["d_100"] if v != "0"]]
        result = select_fraction(training, predictions, orders)
        self.assertFalse(result["candidates"]["d_100"]["eligible"])
        self.assertNotEqual(result["method"], "d_100")


if __name__ == "__main__":
    unittest.main()
