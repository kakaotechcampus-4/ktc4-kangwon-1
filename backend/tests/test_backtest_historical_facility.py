"""의료기관 자료의 부재를 시설 부재로 만들지 않고 하한 기여와 관측을 구분합니다."""

import unittest

from backtest.historical_facility import apply_bounds, medical_floor


class HistoricalFacilityTests(unittest.TestCase):
    def detail(self):
        return {
            "C4_source_status": "unknown",
            "effective_C4_weight": 10,
            "unknown_component_policy_points": 2,
            "policy_aggregate_points": 2,
            "item_contributions": {"D1": 20},
            "applicable_weight": 90,
        }

    def test_no_medical_subset_record_does_not_prove_absence(self):
        r = medical_floor(
            {"required_facilities": "HP8", "max_distance_m": "300"},
            {"latitude": 37.5, "longitude": 127},
            [],
        )
        self.assertFalse(r["available"])
        self.assertIn("not_absence", r["reason"])

    def test_actual_snapshot_point_can_establish_full_lower_bound(self):
        r = medical_floor(
            {"required_facilities": "HP8", "max_distance_m": "300"},
            {"latitude": 37.5, "longitude": 127},
            [{"latitude": 37.5, "longitude": 127, "quarter": "20252"}],
        )
        self.assertEqual(r["minimum_points"], 10)
        self.assertTrue(r["not_exact_nearest_full_category"])

    def test_unknown_weight_and_unrelated_category_policy_remain(self):
        d = self.detail()
        c = {k: {"status": "unknown", "points": None} for k in ("SC4", "HP8")}
        result = apply_bounds(
            d, c, {"SC4": {"available": True, "minimum_points": 8}, "HP8": {"available": False}}
        )
        self.assertEqual(result["effective_C4_contribution"], 5)
        self.assertEqual(result["effective_C4_weight"], 10)
        self.assertEqual(result["C4_source_status"], "unknown")
        self.assertIsNone(result["observed_aggregate_points"])

    def test_wrong_facility_type_cannot_silently_receive_credit(self):
        with self.assertRaises(ValueError):
            apply_bounds(
                self.detail(),
                {"SC4": {"status": "unknown", "points": None}},
                {"HP8": {"available": True, "minimum_points": 10}},
            )
