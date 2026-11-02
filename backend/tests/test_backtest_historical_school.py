"""학교 연도·실제 주소·좌표 불확실성과 C4 미확인 상태의 보존을 확인합니다."""

import unittest

from backtest.historical_school import apply_floor, distance_floor, stable_schools


class HistoricalSchoolTests(unittest.TestCase):
    def row(self, year, **changes):
        return {
            "연도": year,
            "시도": "서울특별시",
            "자치구": "강남구",
            "학교급": "초등학교",
            "학교": "서울검증초등학교",
            "주소": "서울특별시 강남구 검증로 13",
            "위도": "37.5",
            "경도": "127.0",
            **changes,
        }

    def test_only_same_school_and_building_across_both_historical_years_is_used(self):
        a = self.row("2024")
        b = self.row(
            "2025",
            시도="서울특별시교육청",
            주소="서울특별시 강남구 검증로 13(역삼동, 검증초등학교)",
            위도="37.5001",
        )
        result = stable_schools([a, b, self.row("2026")])
        self.assertEqual(len(result["schools"]), 1)
        self.assertEqual(len(result["schools"][0]["coordinate_candidates"]), 2)
        self.assertTrue(result["within_year_continuity_is_assumption"])

    def test_address_subnumber_and_duplicate_identity_cannot_be_silently_matched(self):
        self.assertEqual(
            stable_schools(
                [self.row("2024"), self.row("2025", 주소="서울특별시 강남구 검증로 13-1")]
            )["schools"],
            [],
        )
        self.assertEqual(
            stable_schools([self.row("2024"), self.row("2024"), self.row("2025")])["schools"], []
        )

    def test_kindergarten_and_new_year_only_school_do_not_establish_old_school_presence(self):
        self.assertEqual(stable_schools([self.row("2025")])["schools"], [])
        self.assertEqual(
            stable_schools([self.row("2024", 학교급="유치원"), self.row("2025", 학교급="유치원")])[
                "schools"
            ],
            [],
        )

    def test_worse_annual_coordinate_controls_lower_bound_and_no_hit_is_not_absence(self):
        schools = stable_schools([self.row("2024"), self.row("2025", 위도="37.51")])["schools"]
        p = {"required_facilities": "SC4", "max_distance_m": "500"}
        self.assertFalse(
            distance_floor(p, {"latitude": 37.5, "longitude": 127.0}, schools)["available"]
        )
        self.assertFalse(distance_floor(p, {"latitude": 37.5, "longitude": 127.0}, [])["available"])

    def test_floor_does_not_turn_unknown_into_observed_or_remove_weight(self):
        d = {
            "C4_source_status": "unknown",
            "effective_C4_weight": 10,
            "unknown_component_policy_points": 2,
            "policy_aggregate_points": 2,
            "item_contributions": {"D1": 20},
            "applicable_weight": 90,
            "source_status": {"S1": "unknown"},
        }
        result = apply_floor(
            d,
            {"SC4": {"status": "unknown", "points": None}},
            {"available": True, "minimum_points": 7.5},
        )
        self.assertEqual(result["effective_C4_contribution"], 7.5)
        self.assertEqual(result["C4_source_status"], "unknown")
        self.assertIsNone(result["observed_aggregate_points"])
        self.assertEqual(result["source_status"], d["source_status"])
        self.assertEqual(result["effective_C4_weight"], 10)
