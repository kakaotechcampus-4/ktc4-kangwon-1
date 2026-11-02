"""점수 비교에서 미확인 불이익·배점·순위·단조성이 보존되는지 확인합니다."""

import copy
import unittest

from app.agentic.scoring import WEIGHTS, result
from backtest.followup import C_ITEMS
from backtest.rank_calibration import apply_calibration, reference_for
from backtest.rank_demand import apply_demand
from backtest.rank_experiment import exposure
from backtest.rank_market import apply_market
from backtest.rank_variant import Variant, order_rows, s_grade, score_row


def fixture(code="a"):
    return {
        "code": code,
        "items": {k: result(k, 2, value=1.0) for k in C_ITEMS},
        "coverage": 0.8,
        "regulation": "unknown",
        "space": {"adjustment": 0, "excluded": False},
    }


class VariantTests(unittest.TestCase):
    def test_shrink_changes_c1_only_and_keeps_input(self):
        row = fixture()
        row["items"]["C1"] = result("C1", 4, value=2.0)
        frozen = copy.deepcopy(row)
        half = score_row(row, Variant("half", c1_strength=0.5))
        self.assertEqual(half["item_grades"]["C1"], 3)
        self.assertEqual(half["item_points"]["C1"], 11.25)
        for key in C_ITEMS:
            if key != "C1":
                self.assertEqual(half["item_points"][key], row["items"][key]["points"])
        self.assertEqual(row, frozen)

    def test_unknown_stays_in_denominator_and_na_is_removed(self):
        row = fixture()
        row["items"]["S1"] = result("S1")
        row["items"]["D1"] = result("D1", status="n.a.")
        value = score_row(row, Variant("test", c1_strength=0, s_curve="ratio"))
        self.assertEqual(value["applicable"], 70)
        self.assertIsNone(value["item_points"]["S1"])
        self.assertIsNone(value["item_points"]["D1"])
        self.assertAlmostEqual(value["normalized"], 80 * value["points"] / 70)
        # 실제 관측된 0점은 미확인으로 바꾸지 않습니다.
        row["items"]["S1"] = result("S1", 0, value=3)
        current = score_row(row, Variant("current"))
        self.assertEqual(current["item_points"]["S1"], 0)

    def test_profile_fixed_c1_keeps_same_points(self):
        row = fixture()
        row["items"]["C1"] = result("C1", 2, value=None)
        for strength in (0, 0.5, 1):
            value = score_row(row, Variant("test", c1_strength=strength))
            self.assertEqual(value["item_points"]["C1"], 7.5)

    def test_s_curves_are_bounded_and_monotone_in_correct_direction(self):
        for curve in ("linear5", "linear2", "ratio"):
            for item in ("S1", "S2", "S3", "S4"):
                ratios = (-10, -1, 0, 0.5, 1, 2, 10) if item == "S2" else (0, 0.5, 1, 2, 10)
                values = [s_grade(item, r, curve) for r in ratios]
                self.assertTrue(all(0 <= v <= 4 for v in values))
                self.assertEqual(values, sorted(values, reverse=item != "S2"))
                self.assertEqual(s_grade(item, 1, curve), 2)
        self.assertGreater(s_grade("S1", 3, "ratio"), s_grade("S1", 3, "linear2"))

    def test_invalid_and_fabricated_observations_are_rejected(self):
        for variant in (Variant("bad", c1_strength=-1), Variant("bad", s_curve="unknown")):
            with self.assertRaises(ValueError):
                score_row(fixture(), variant)
        row = fixture()
        row["items"]["S1"] = result("S1")
        row["items"]["S1"]["points"] = 0
        with self.assertRaises(ValueError):
            score_row(row, Variant("test"))
        for ratio in (float("nan"), -1):
            with self.assertRaises(ValueError):
                s_grade("S1", ratio, "ratio")

    def test_order_preserves_coverage_tie_and_exclusion(self):
        rows = [fixture(c) for c in ("b", "a", "blocked")]
        rows[0]["coverage"] = 0.9
        rows[2]["space"]["excluded"] = True
        values = {r["code"]: score_row(r, Variant("current")) for r in rows}
        self.assertEqual(order_rows(rows, values), ["b", "a"])
        self.assertEqual(order_rows(rows, values, {"a"}), ["a"])

    def test_score_weight_total_and_exposure_include_never_recommended(self):
        self.assertEqual(sum(WEIGHTS[k] for k in C_ITEMS), 80)
        value = score_row(fixture(), Variant("current"))
        self.assertEqual(value["normalized"], 40)
        observed = exposure([["a", "b"], ["a", "c"]], {"a", "b", "c", "d"}, 2)
        self.assertEqual(observed["slots"], 4)
        self.assertEqual(observed["never_n"], 1)
        self.assertEqual(observed["max_locations"], 2)
        self.assertAlmostEqual(observed["hhi"], 0.375)


class CalibrationTests(unittest.TestCase):
    def records(self):
        return [
            {
                "id": str(i),
                "cluster": "area" + str(i),
                "site": {"latitude": 37.7 + i * 0.0001, "longitude": 127.0},
                "scores": [fixture()],
            }
            for i in range(25)
        ]

    def test_reference_excludes_same_area_and_nearby_without_labels(self):
        records = self.records()
        site = {"latitude": 37.5, "longitude": 127.0}
        records[0]["cluster"] = "held"
        records[1]["site"] = site
        reference = reference_for(records, site, "held")
        self.assertEqual(reference["excluded_ids"], ["0", "1"])
        self.assertEqual(len(reference["values"][("a", "S1")]), 23)
        changed = copy.deepcopy(records)
        for record in changed:
            record["target"] = "different_label"
        self.assertEqual(reference_for(changed, site, "held"), reference)

    def test_cluster_is_counted_once_and_sparse_reference_keeps_base(self):
        records = self.records()
        for record in records:
            record["cluster"] = "same"
        reference = reference_for(records, {"latitude": 37.5, "longitude": 127.0}, "held")
        self.assertEqual(len(reference["values"][("a", "S1")]), 1)
        row = fixture()
        base = score_row(row, Variant("ratio", s_curve="ratio"))
        calibrated = apply_calibration(row, base, reference, "cal_S_half")
        self.assertEqual(calibrated["item_points"], base["item_points"])

    def test_calibration_keeps_unknown_na_fixed_and_denominator(self):
        row = fixture()
        row["items"]["S1"] = result("S1")
        row["items"]["D1"] = result("D1", status="n.a.")
        row["items"]["C1"] = result("C1", 2, value=None)
        reference = reference_for(self.records(), {"latitude": 37.5, "longitude": 127.0}, "held")
        base = score_row(row, Variant("ratio", s_curve="ratio"))
        calibrated = apply_calibration(row, base, reference, "cal_both_half")
        self.assertIsNone(calibrated["item_points"]["S1"])
        self.assertIsNone(calibrated["item_points"]["D1"])
        self.assertEqual(calibrated["item_points"]["C1"], 7.5)
        self.assertEqual(calibrated["applicable"], 70)

    def test_midrank_ties_and_s_direction_are_preserved(self):
        reference = {"values": {("a", "S1"): [-2] * 10 + [-1] * 10}}
        row = fixture()
        base = score_row(row, Variant("ratio", s_curve="ratio"))
        calibrated = apply_calibration(row, base, reference, "cal_S_full")
        self.assertEqual(calibrated["item_grades"]["S1"], 3)
        row["items"]["S1"] = result("S1", 0, value=3)
        lower = apply_calibration(
            row, score_row(row, Variant("ratio", s_curve="ratio")), reference, "cal_S_full"
        )
        self.assertLess(lower["item_points"]["S1"], calibrated["item_points"]["S1"])


class MarketTests(unittest.TestCase):
    def test_lq_changes_only_measured_c1_and_keeps_missing_penalty(self):
        row = fixture()
        row["items"]["S1"] = result("S1")
        frozen = copy.deepcopy(row)
        base = score_row(row, Variant("current"))
        data = {"commercial_area": {"by_middle": [{"code": "a", "lq": 3.0}]}}
        value = apply_market(row, base, data, "lq_half")
        self.assertEqual(value["item_grades"]["C1"], 2.5)
        self.assertIsNone(value["item_points"]["S1"])
        self.assertEqual(value["applicable"], 80)
        for name in C_ITEMS:
            if name != "C1":
                self.assertEqual(value["item_points"][name], base["item_points"][name])
        self.assertEqual(row, frozen)

    def test_unknown_and_policy_fixed_c1_cannot_be_filled_from_lq(self):
        for item in (result("C1"), result("C1", 2, value=None)):
            row = fixture()
            row["items"]["C1"] = item
            base = score_row(row, Variant("current"))
            self.assertEqual(apply_market(row, base, {}, "lq_full"), base)

    def test_market_grade_is_bounded_monotone_and_zero_is_real(self):
        row = fixture()
        base = score_row(row, Variant("current"))
        values = []
        for lq in (0, 0.5, 1, 2, 100):
            data = {"commercial_area": {"by_middle": [{"code": "a", "lq": lq}]}}
            value = apply_market(row, base, data, "lq_full")
            values.append(value["item_grades"]["C1"])
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[0], 0)
        self.assertEqual(values[2], 2)
        self.assertTrue(all(0 <= v < 4 for v in values))
        with self.assertRaises(ValueError):
            apply_market(row, base, {"commercial_area": {"by_middle": []}}, "lq_full")


class DemandTests(unittest.TestCase):
    def test_combines_only_two_observed_d1_components(self):
        row = fixture()
        row["items"]["D1"] = result("D1", 1, value={"r": 1.3, "p": 30})
        frozen = copy.deepcopy(row)
        base = score_row(row, Variant("current"))
        geometric = apply_demand(row, base, "d1_geometric")
        average = apply_demand(row, base, "d1_mean")
        self.assertEqual(geometric["item_grades"]["D1"], 2)
        self.assertEqual(average["item_grades"]["D1"], 2.5)
        self.assertEqual(geometric["applicable"], base["applicable"])
        self.assertEqual(row, frozen)
        for key in C_ITEMS:
            if key != "D1":
                self.assertEqual(geometric["item_points"][key], base["item_points"][key])

    def test_unknown_na_and_single_scale_d1_are_not_filled(self):
        for item in (result("D1"), result("D1", status="n.a."), result("D1", 2, value=123)):
            row = fixture()
            row["items"]["D1"] = item
            base = score_row(row, Variant("current"))
            self.assertEqual(apply_demand(row, base, "d1_mean"), base)

    def test_geometric_keeps_zero_for_a_zero_component(self):
        row = fixture()
        row["items"]["D1"] = result("D1", 0, value={"r": 0.7, "p": 90})
        base = score_row(row, Variant("current"))
        self.assertEqual(apply_demand(row, base, "d1_geometric")["item_points"]["D1"], 0)
