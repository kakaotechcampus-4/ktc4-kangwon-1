"""51업종 공간 추정치와 명시 답변만 사용하는 비교를 검증합니다."""

import csv
import unittest

from app.agentic.space import compare_space
from app.industries import DATA_DIR
from app.industries.catalog import INDUSTRIES


class SpaceEstimatesTests(unittest.TestCase):
    def setUp(self):
        with (DATA_DIR / "industry_space_requirements.csv").open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            self.profiles = {row["industry_code"]: row for row in csv.DictReader(handle)}

    def test_all_profiles_have_explicit_area_and_operational_water_estimates(self):
        self.assertEqual(set(self.profiles), set(INDUSTRIES))
        for code, profile in self.profiles.items():
            with self.subTest(code=code):
                self.assertRegex(profile["area_band"], r"^[1-9]\d*~[1-9]\d*㎡$")
                low, high = map(int, profile["area_band"].rstrip("㎡").split("~"))
                self.assertLess(low, high)
                self.assertIn(profile["water_supply_needed"], {"true", "false"})
                self.assertEqual(profile["reviewed"], "false")
                self.assertEqual(profile["confidence"], "low")
                for area, expected in ((low, "일치"), (high, "일치"), (high + 1, "불일치")):
                    result = compare_space(profile, {"exclusive_area": f"{area}㎡"})
                    self.assertEqual(result["area"], expected)
                unanswered = compare_space(profile, {})
                self.assertEqual(unanswered["area"], "미확인")
                for field in ("floor", "kitchen", "ventilation", "water_supply"):
                    key = "floor_preference" if field == "floor" else field + "_needed"
                    expected = "해당 없음" if profile[key] == "false" else "미확인"
                    self.assertEqual(unanswered[field], expected)
                for answer, expected in (("있음", "일치"), ("없음", "불일치")):
                    result = compare_space(profile, {"existing_facilities": f"급배수 {answer}"})
                    self.assertEqual(
                        result["water_supply"],
                        expected if profile["water_supply_needed"] == "true" else "해당 없음",
                    )

    def test_retail_absent_cooking_equipment_cannot_be_adverse(self):
        for code, profile in self.profiles.items():
            if code.startswith("G"):
                with self.subTest(code=code):
                    result = compare_space(profile, {"existing_facilities": "주방·배기 없음"})
                    self.assertEqual(result["kitchen"], "해당 없음")
                    self.assertEqual(result["ventilation"], "해당 없음")
                    self.assertEqual(profile["floor_preference"], "1층 접근 우선 가정")
        self.assertEqual(self.profiles["G204"]["water_supply_needed"], "false")
        self.assertEqual(self.profiles["G219"]["water_supply_needed"], "true")
        self.assertEqual(self.profiles["I212"]["water_supply_needed"], "true")

    def test_area_unit_conversion_and_equivalent_parenthetical_units(self):
        for requirement, answer, expected in (
            ("20~40㎡", "약40㎡(12평)", "일치"),
            ("20~40㎡", "약 40㎡ (약 12평)", "일치"),
            ("20~40㎡", "12평", "일치"),
            ("10~15평", "40m²", "일치"),
            ("20~40㎡", "30평", "불일치"),
            ("20~40㎡", "40㎡(20평)", "미확인"),
            ("20~40㎡", "전용40㎡, 공용12평", "미확인"),
            ("20~40㎡", "아마40㎡", "미확인"),
            ("20~40㎡", "0㎡", "미확인"),
            ("40~20㎡", "30㎡", "미확인"),
        ):
            with self.subTest(requirement=requirement, answer=answer):
                self.assertEqual(
                    compare_space({"area_band": requirement}, {"exclusive_area": answer})["area"],
                    expected,
                )
