"""가중치 선택의 공간 분리·자료 부족 불이익·검증 정답 비사용을 확인합니다."""

import copy
import math
import unittest

from app.agentic.scoring import WEIGHTS
from backtest.followup import C_ITEMS
from backtest.weight_selection import (
    CONFIGURATIONS,
    CURRENT,
    EXTENDED_GRID,
    ORIGINAL_WEIGHTS,
    WEIGHT_GRID,
    assign_folds,
    features_for,
    negative_log_probability,
    select_configuration,
    split_training,
    weighted_score,
)


def source_value():
    status = {n: "observed" for n in C_ITEMS}
    status.update(D1="n.a.", S1="unknown")
    points = {n: WEIGHTS[n] / 2 if s == "observed" else None for n, s in status.items()}
    total = sum(v for v in points.values() if v is not None)
    applicable = 80 - WEIGHTS["D1"]
    return status, {
        "item_points": points,
        "points": total,
        "applicable": applicable,
        "normalized": 80 * total / applicable,
    }


class WeightScoreTests(unittest.TestCase):
    def test_extended_grid_retains_original_and_missing_data_penalty(self):
        self.assertTrue(set(WEIGHT_GRID) <= set(EXTENDED_GRID))
        self.assertTrue(all(sum(w) == 80 and w[2] >= 15 and min(w) >= 5 for w in EXTENDED_GRID))
        status, value = source_value()
        features = features_for(status, value)
        with self.assertRaises(ValueError):
            weighted_score(features, (5, 60, 15))
        adjusted = weighted_score(features, (5, 60, 15), EXTENDED_GRID)
        self.assertGreater(adjusted["applicable"], 15)
        with self.assertRaises(ValueError):
            weighted_score(features, (35, 45, 0), ((35, 45, 0),))

    def test_original_weights_reproduce_frozen_score_and_source_is_not_mutated(self):
        status, value = source_value()
        original = copy.deepcopy((status, value))
        features = features_for(status, value)
        result = weighted_score(features, ORIGINAL_WEIGHTS)
        self.assertEqual(result["normalized"], value["normalized"])
        self.assertEqual(result["applicable"], value["applicable"])
        self.assertEqual((status, value), original)

    def test_unknown_weight_remains_in_denominator_for_every_predeclared_weight(self):
        status, value = source_value()
        unknown = features_for(status, value)
        observed = copy.deepcopy(unknown)
        observed["status"]["S1"] = "observed"
        observed["observed"]["S1"] = 7.5
        observed["frozen_score"] += 80 * 7.5 / value["applicable"]
        for weights in WEIGHT_GRID:
            low, high = weighted_score(unknown, weights), weighted_score(observed, weights)
            self.assertEqual(low["applicable"], high["applicable"])
            self.assertGreater(high["normalized"], low["normalized"])
            self.assertGreaterEqual(weights[2], 15)
            self.assertLess(low["applicable"], 80)

    def test_estimated_contribution_stays_separate_and_not_applicable_cannot_be_filled(self):
        status, value = source_value()
        value.update(
            estimated_item_points={"S1": 1},
            points=value["points"] + 1,
            normalized=value["normalized"] + 80 / value["applicable"],
        )
        features = features_for(status, value)
        result = weighted_score(features, (50, 15, 15))
        self.assertEqual(result["estimated_points"], 0.5)
        self.assertIsNone(features["observed"]["S1"])
        value["estimated_item_points"]["D1"] = 1
        with self.assertRaises(ValueError):
            features_for(status, value)

    def test_changed_original_point_or_unknown_score_is_rejected(self):
        status, value = source_value()
        value["item_points"]["S1"] = 0
        with self.assertRaises(ValueError):
            features_for(status, value)
        status, value = source_value()
        value["points"] += 1
        with self.assertRaises(ValueError):
            features_for(status, value)


class WeightSelectionTests(unittest.TestCase):
    def locations(self):
        return [
            {
                "id": str(i),
                "district": str(i % 6),
                "cluster": str(i),
                "site": {"latitude": 37 + i * 0.02, "longitude": 127},
                "target": "A",
            }
            for i in range(18)
        ]

    def test_district_folds_ignore_labels_and_input_order(self):
        locations = self.locations()
        folds = assign_folds(locations)
        changed = [{**v, "target": "different"} for v in reversed(locations)]
        self.assertEqual(folds, assign_folds(changed))
        for district in {c["district"] for c in locations}:
            self.assertEqual(
                len({folds[c["id"]] for c in locations if c["district"] == district}), 1
            )

    def test_training_excludes_same_district_area_and_nearby_cross_border(self):
        locations = self.locations()
        locations[1]["site"] = locations[0]["site"]
        locations[2]["cluster"] = locations[0]["cluster"]
        split = split_training(locations, {"0"})
        self.assertEqual(split["excluded_ids"]["1"], "within1000m_of_evaluation")
        self.assertEqual(split["excluded_ids"]["2"], "same_market_area")
        self.assertEqual(split["excluded_ids"]["6"], "same_district")
        self.assertNotIn("0", split["training_ids"])
        self.assertTrue(split["training_ids"])

    def setup_selection(self):
        cases = [{"id": "1", "target": "A", "cluster": "one"}]
        codes = list("ABCDEFGHIJK")
        predictions = {
            "1": {c.name: {code: float(code == "A") for code in codes} for c in CONFIGURATIONS}
        }
        orders = {"1": {c.name: codes[:] for c in CONFIGURATIONS}}
        return cases, predictions, orders

    def test_selection_cannot_use_labels_outside_training_subset(self):
        cases, predictions, orders = self.setup_selection()
        before = select_configuration(cases, predictions, orders)
        predictions["unseen"] = {c.name: {"unknown": 999} for c in CONFIGURATIONS}
        orders["unseen"] = {c.name: ["unknown"] for c in CONFIGURATIONS}
        self.assertEqual(before, select_configuration(cases, predictions, orders))
        self.assertEqual(before["configuration"], CURRENT)

    def test_better_training_loss_cannot_bypass_exposure_constraint(self):
        cases = [{"id": key, "target": "A", "cluster": key} for key in ("1", "2")]
        codes = list("ABCDEFGHIJK")
        predictions = {
            key: {
                c.name: {code: 10 - i if key == "1" else i for i, code in enumerate(codes)}
                for c in CONFIGURATIONS
            }
            for key in ("1", "2")
        }
        bad = next(c.name for c in CONFIGURATIONS if c.name != CURRENT)
        for key in predictions:
            predictions[key][bad]["A"] = 80
        orders = {
            key: {
                c.name: sorted(codes, key=lambda code: -predictions[key][c.name][code])
                for c in CONFIGURATIONS
            }
            for key in predictions
        }
        result = select_configuration(cases, predictions, orders)
        self.assertLess(
            result["candidates"][bad]["cluster_mean_log_loss"],
            result["candidates"][CURRENT]["cluster_mean_log_loss"],
        )
        self.assertFalse(result["candidates"][bad]["eligible"])
        self.assertEqual(result["configuration"], CURRENT)

    def test_log_loss_is_finite_for_extreme_scores_and_has_known_equal_score_value(self):
        self.assertAlmostEqual(negative_log_probability({"A": 0, "B": 0}, "A"), math.log(2))
        self.assertTrue(math.isfinite(negative_log_probability({"A": 1e8, "B": -1e8}, "B")))


if __name__ == "__main__":
    unittest.main()
