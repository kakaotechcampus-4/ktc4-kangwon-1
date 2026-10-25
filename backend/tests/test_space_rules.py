"""확인 화면 공간 값으로 업종을 빼거나 순위를 조정하는 규칙을 검증합니다."""

import unittest

from app.agentic.space_rules import FACILITY_NAMES, SpaceJudgement, judge, load_requirements
from app.industries.catalog import INDUSTRIES


def profile(**levels):
    base = {
        "kitchen_needed": "false",
        "ventilation_needed": "false",
        "water_supply_needed": "false",
        "floor_preference": "false",
        "area_band": "40~150㎡",
    }
    return {**base, **levels}


def facilities(**states):
    return {"confirmed_facilities": states}


class FacilityRuleTests(unittest.TestCase):
    def test_required_unavailable_excludes(self):
        result = judge(
            profile(ventilation_needed="required"), facilities(ventilation="unavailable")
        )
        self.assertTrue(result.excluded)
        self.assertEqual(result.exclusion_reasons, ("배기(덕트) 설치 불가",))
        self.assertEqual(result.adjustment, 0)

    def test_required_present_is_clean(self):
        result = judge(profile(kitchen_needed="required"), facilities(kitchen="present"))
        self.assertEqual(result, SpaceJudgement(False, (), 0, ()))

    def test_required_installable_notes_work(self):
        result = judge(profile(kitchen_needed="required"), facilities(kitchen="installable"))
        self.assertFalse(result.excluded)
        self.assertEqual(result.notes, ("주방 설치 공사 필요",))
        self.assertEqual(result.adjustment, 0)

    def test_required_unknown_notes_check(self):
        result = judge(profile(water_supply_needed="required"), {})
        self.assertFalse(result.excluded)
        self.assertEqual(result.notes, ("급배수 확인 필요",))

    def test_preferred_unavailable_minus_five(self):
        result = judge(
            profile(ventilation_needed="preferred"), facilities(ventilation="unavailable")
        )
        self.assertFalse(result.excluded)
        self.assertEqual(result.adjustment, -5)
        self.assertEqual(result.notes, ())

    def test_preferred_installable_and_present_are_clean(self):
        for state in ("installable", "present"):
            with self.subTest(state=state):
                result = judge(
                    profile(ventilation_needed="preferred"), facilities(ventilation=state)
                )
                self.assertEqual(result, SpaceJudgement(False, (), 0, ()))

    def test_preferred_unknown_notes_check(self):
        result = judge(profile(ventilation_needed="preferred"), {})
        self.assertEqual(result.notes, ("배기(덕트) 확인 필요",))

    def test_conditional_unavailable_note_only(self):
        result = judge(
            profile(ventilation_needed="conditional"), facilities(ventilation="unavailable")
        )
        self.assertFalse(result.excluded)
        self.assertEqual(result.adjustment, 0)
        self.assertEqual(result.notes, ("배기(덕트) 설치 불가: 메뉴·작업 방식 확인 필요",))

    def test_conditional_present_and_installable_are_clean(self):
        for state in ("present", "installable"):
            with self.subTest(state=state):
                result = judge(profile(kitchen_needed="conditional"), facilities(kitchen=state))
                self.assertEqual(result, SpaceJudgement(False, (), 0, ()))

    def test_conditional_unknown_notes_check(self):
        result = judge(profile(kitchen_needed="conditional"), {})
        self.assertEqual(result.notes, ("주방 확인 필요",))

    def test_not_applicable_facility_is_ignored(self):
        result = judge(profile(), facilities(kitchen="unavailable", ventilation="unavailable"))
        self.assertEqual(result, SpaceJudgement(False, (), 0, ()))

    def test_unexpected_state_is_unknown(self):
        result = judge(profile(kitchen_needed="required"), facilities(kitchen="maybe"))
        self.assertFalse(result.excluded)
        self.assertEqual(result.notes, ("주방 확인 필요",))

    def test_free_text_is_ignored(self):
        result = judge(profile(ventilation_needed="required"), {"existing_facilities": "배기 없음"})
        self.assertFalse(result.excluded)
        self.assertEqual(result.notes, ("배기(덕트) 확인 필요",))

    def test_facility_names(self):
        self.assertEqual(
            FACILITY_NAMES,
            {"kitchen": "주방", "ventilation": "배기(덕트)", "water_supply": "급배수"},
        )


class FloorRuleTests(unittest.TestCase):
    def test_ground_required_upper_floor_excludes(self):
        for floor in ("2층", "4층", "지하 1층"):
            with self.subTest(floor=floor):
                result = judge(profile(floor_preference="ground_required"), {"floor": floor})
                self.assertTrue(result.excluded)
                self.assertEqual(result.exclusion_reasons, ("1층이 아님",))

    def test_ground_required_first_floor_is_clean(self):
        result = judge(profile(floor_preference="ground_required"), {"floor": "1층"})
        self.assertEqual(result, SpaceJudgement(False, (), 0, ()))

    def test_ground_preferred_penalties(self):
        for floor, expected in (
            ("1층", 0),
            ("2층", -5),
            ("3층", -7),
            ("4층", -10),
            ("7층", -10),
            ("지하 1층", -3),
            ("지하 2층", -10),
        ):
            with self.subTest(floor=floor):
                result = judge(profile(floor_preference="ground_preferred"), {"floor": floor})
                self.assertFalse(result.excluded)
                self.assertEqual(result.adjustment, expected)
                self.assertEqual(result.notes, ())

    def test_basement_preferred_plus_three(self):
        for floor, expected in (("지하 1층", 3), ("지하 2층", 3), ("1층", 0), ("3층", 0)):
            with self.subTest(floor=floor):
                result = judge(profile(floor_preference="basement_preferred"), {"floor": floor})
                self.assertEqual(result.adjustment, expected)
                self.assertEqual(result.notes, ())

    def test_floor_not_applicable_is_ignored(self):
        result = judge(profile(), {"floor": "5층"})
        self.assertEqual(result, SpaceJudgement(False, (), 0, ()))

    def test_unreadable_floor_is_unknown(self):
        for level in ("ground_required", "ground_preferred"):
            for floor in ("중1층", "", None, "아마 1층"):
                with self.subTest(level=level, floor=floor):
                    answers = {} if floor is None else {"floor": floor}
                    result = judge(profile(floor_preference=level), answers)
                    self.assertFalse(result.excluded)
                    self.assertEqual(result.adjustment, 0)
                    self.assertEqual(result.notes, ("층 확인 필요",))
        result = judge(profile(floor_preference="basement_preferred"), {"floor": "중1층"})
        self.assertEqual(result, SpaceJudgement(False, (), 0, ()))


class AreaAndCombinedRuleTests(unittest.TestCase):
    def test_area_out_of_band_note_only(self):
        result = judge(profile(), {"exclusive_area": "15㎡"})
        self.assertFalse(result.excluded)
        self.assertEqual(result.adjustment, 0)
        self.assertEqual(result.notes, ("면적이 업종 일반 범위(40~150㎡) 밖",))

    def test_area_inside_band_and_unknown_have_no_note(self):
        for answers in ({"exclusive_area": "52㎡"}, {}, {"exclusive_area": "넓음"}):
            with self.subTest(answers=answers):
                self.assertEqual(judge(profile(), answers).notes, ())

    def test_combined_order_and_totals(self):
        result = judge(
            profile(
                kitchen_needed="required",
                ventilation_needed="preferred",
                water_supply_needed="required",
                floor_preference="ground_preferred",
            ),
            {
                "floor": "3층",
                "exclusive_area": "15㎡",
                "confirmed_facilities": {
                    "ventilation": "unavailable",
                    "water_supply": "installable",
                },
            },
        )
        self.assertFalse(result.excluded)
        self.assertEqual(result.adjustment, -12)
        self.assertEqual(
            result.notes,
            ("주방 확인 필요", "급배수 설치 공사 필요", "면적이 업종 일반 범위(40~150㎡) 밖"),
        )


class RequirementTableTests(unittest.TestCase):
    def test_load_requirements_covers_all_industries(self):
        rows = load_requirements()
        self.assertEqual(set(rows), set(INDUSTRIES))
        self.assertEqual(rows["I201"]["ventilation_needed"], "required")

    def test_real_profiles_match_mentor_examples(self):
        rows = load_requirements()
        korean = judge(rows["I201"], facilities(ventilation="unavailable"))
        self.assertTrue(korean.excluded)
        car = next(row for row in rows.values() if row["industry_name"] == "자동차 수리·세차")
        self.assertTrue(judge(car, {"floor": "4층"}).excluded)
        cafe = next(row for row in rows.values() if row["industry_name"] == "카페·비알코올 음료점")
        self.assertEqual(judge(cafe, {"floor": "4층"}).adjustment, -10)
