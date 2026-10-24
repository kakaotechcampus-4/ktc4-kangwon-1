"""규칙이 채점하는 공간 근거를 L이 다시 쓰지 못하게 막는 판정을 검증합니다."""

import json
import unittest

from app.agentic.report import rule_scored_space


def fact(metric, source="industry_profile", value=None):
    return {"metric": metric, "source": source, "value_json": json.dumps(value)}


class RuleScoredSpaceTests(unittest.TestCase):
    def test_l_rejects_floor_space_fit(self):
        self.assertTrue(rule_scored_space(fact("space_fit"), "floor", "G204"))

    def test_l_rejects_required_facility(self):
        self.assertTrue(rule_scored_space(fact("space_fit"), "ventilation", "I201"))
        self.assertTrue(rule_scored_space(fact("space_fit"), "kitchen", "I201"))

    def test_l_rejects_preferred_facility(self):
        self.assertTrue(rule_scored_space(fact("space_fit"), "ventilation", "S204"))

    def test_l_accepts_area_and_conditional_facility(self):
        self.assertFalse(rule_scored_space(fact("space_fit"), "area", "I201"))
        self.assertFalse(rule_scored_space(fact("space_fit"), "kitchen", "I212"))
        self.assertFalse(rule_scored_space(fact("space_fit"), "ventilation", "I212"))
        self.assertFalse(rule_scored_space(fact("space_fit"), None, "I201"))

    def test_l_rejects_user_floor_fact(self):
        self.assertTrue(rule_scored_space(fact("floor", "user", "4층"), None, "S209"))

    def test_l_rejects_confirmed_facilities_but_not_free_text(self):
        confirmed = fact("existing_facilities", "user", {"ventilation": "unavailable"})
        self.assertTrue(rule_scored_space(confirmed, None, "I201"))
        free_text = fact("existing_facilities", "user", "배기 없음")
        self.assertFalse(rule_scored_space(free_text, None, "I201"))

    def test_other_facts_are_untouched(self):
        self.assertFalse(rule_scored_space(fact("place_name", "map", "가게"), None, "I201"))
        self.assertFalse(rule_scored_space(fact("space_condition", "user", "지상"), None, "I201"))
