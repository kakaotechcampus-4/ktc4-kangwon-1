"""지도 검색 일치의 세 상태를 모델 호출 없이 검증합니다."""

import unittest

from app.agents.map_analysis.matching import RULE_VERSION, distance_m, match_place
from app.industries.lookup import industry_terms


class MatchingTests(unittest.TestCase):
    def test_distance_preserves_missing_and_invalid_values(self):
        self.assertEqual(distance_m({"distance": "45.8"}), 45)
        self.assertEqual(distance_m({"distance": 0}), 0)
        for value in (None, {}, "bad", -1, "-1", float("nan"), float("inf")):
            with self.subTest(value=value):
                self.assertIsNone(distance_m({"distance": value}))

    def test_category_name_and_unknown_are_distinct(self):
        self.assertEqual(
            match_place("I212", "가게", "기타", "CE7"),
            ("category_match", RULE_VERSION + ":category"),
        )
        term = industry_terms("I212")["includes"][0].split("/")[0]
        self.assertEqual(
            match_place("I212", "가게", term, ""),
            ("category_match", RULE_VERSION + ":category-term"),
        )
        self.assertEqual(
            match_place("I212", term, "기타", ""), ("name_match", RULE_VERSION + ":name-term")
        )
        self.assertEqual(match_place("I212", "전혀 다른 가게", "기타", ""), ("unknown", None))

    def test_facility_requires_the_exact_category(self):
        self.assertEqual(
            match_place("I212", "학교", "학교", "SC4", "SC4"),
            ("category_match", RULE_VERSION + ":facility"),
        )
        self.assertEqual(match_place("I212", "학교", "학교", "AC5", "SC4"), ("unknown", None))
