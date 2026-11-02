"""C4 결합의 고정 배점·결측 상태·평가 라벨 격리를 확인합니다."""

import copy
import unittest

from backtest.c4_blend import CONFIGURATIONS, score_blend, select_blend


class C4BlendTests(unittest.TestCase):
    def inputs(self):
        common = {
            "retained_D75": {"G215": 40, "I201": 50},
            "balanced57": {"G215": 50, "I201": 40},
            "accuracy64": {"G215": 60, "I201": 30},
        }
        profiles = {
            "G215": {"required_facilities": "HP8", "required_facilities_confidence": "low"},
            "I201": {"required_facilities": ""},
        }
        parts = {"G215": {"HP8": {"status": "unknown", "points": None}}, "I201": {}}
        return common, {"G215": 80, "I201": 80}, profiles, parts

    def test_combines_common80_before_C4_and_keeps_unknown_separate(self):
        args = self.inputs()
        before = copy.deepcopy(args)
        config = next(c for c in CONFIGURATIONS if c.name == "retained_accuracy50")
        result = score_blend(*args, config)
        self.assertEqual(result["common80"]["G215"], 50)
        self.assertEqual(result["C4_details"]["G215"]["source_status"], "unknown")
        self.assertIsNone(result["C4_details"]["G215"]["observed_aggregate_points"])
        self.assertEqual(result["C4_details"]["G215"]["effective_C4_weight"], 5)
        self.assertEqual(args, before)

    def test_non_applicable_C4_has_no_imputed_points_in_any_configuration(self):
        for config in CONFIGURATIONS:
            with self.subTest(config=config.name):
                result = score_blend(*self.inputs(), config)
                detail = result["C4_details"]["I201"]
                self.assertEqual(detail["source_status"], "n.a.")
                self.assertEqual(detail["effective_C4_contribution"], 0)
                self.assertAlmostEqual(
                    result["values"]["I201"], result["common80"]["I201"] * 90 / 80
                )

    def test_positive_combination_stays_between_two_common80_scores(self):
        args = self.inputs()
        for config in CONFIGURATIONS:
            result = score_blend(*args, config)
            for code, value in result["common80"].items():
                ends = (args[0][config.anchor][code], args[0]["accuracy64"][code])
                self.assertGreaterEqual(value, min(ends))
                self.assertLessEqual(value, max(ends))

    def selection_inputs(self):
        cases = [{"id": "train", "target": "I201", "cluster": "train-area"}]
        predictions = {"train": {c.name: {"I201": 50, "G204": 40} for c in CONFIGURATIONS}}
        orders = {"train": {c.name: ["I201", "G204"] for c in CONFIGURATIONS}}
        return cases, predictions, orders

    def test_selection_ignores_unprovided_held_labels_and_predictions(self):
        training, predictions, orders = self.selection_inputs()
        original = select_blend(training, predictions, orders)
        predictions["held"] = {"unused": {"arbitrary": -999}}
        orders["held"] = {"unused": ["arbitrary"]}
        self.assertEqual(select_blend(training, predictions, orders), original)
        self.assertFalse(original["selection_uses_held_labels"])

    def test_duplicate_training_and_missing_candidates_are_rejected(self):
        training, predictions, orders = self.selection_inputs()
        with self.assertRaises(ValueError):
            select_blend(training * 2, predictions, orders)
        orders["train"][CONFIGURATIONS[-1].name] = ["G204", "G204"]
        with self.assertRaises(ValueError):
            select_blend(training, predictions, orders)


if __name__ == "__main__":
    unittest.main()
