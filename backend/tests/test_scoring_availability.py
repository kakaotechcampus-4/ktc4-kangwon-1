"""미지원과 관측량 부족을 구분하고 자료 범위 안내가 점수를 바꾸지 않는지 확인합니다."""

import copy
import unittest

from app.agentic.availability import classify_item, coverage_notes
from app.agentic.scoring import WEIGHTS, result, summarize
from app.industries.catalog import INDUSTRIES_WITHOUT_SEOUL


class AvailabilityTests(unittest.TestCase):
    def test_source_unsupported_is_not_observed_zero_or_non_applicable(self):
        missing = result("S1", reason="서울 대응 업종 없음")
        self.assertEqual(classify_item("M107", "S1", missing), "unsupported_source")
        self.assertEqual(classify_item("M107", "S1", result("S1", 0)), "observed")
        self.assertEqual(classify_item("M107", "S1", result("S1", status="n.a.")), "not_applicable")

    def test_local_exposure_shortage_does_not_become_unsupported_source(self):
        missing = result("S1", reason="개폐업 전체 점포·분기 노출량 부족")
        self.assertEqual(classify_item("G204", "S1", missing), "insufficient_exposure")
        legacy = result("S1", reason="개폐업 관측·전체 노출량 부족")
        self.assertEqual(classify_item("G204", "S1", legacy), "lifecycle_observation_shortage")

    def test_fixed_profile_grade_is_separate_from_field_measurement(self):
        fixed = result("C1", 2, agglomeration="무관")
        measured = result("C1", 2, agglomeration="근처형", value=1)
        self.assertEqual(classify_item("M103", "C1", fixed), "profile_fixed")
        self.assertEqual(classify_item("G204", "C1", measured), "observed")

    def test_sparse_density_baseline_is_identified(self):
        missing = result("C1", reason="희소 기준선·밀도 결측", agglomeration="근처형")
        self.assertEqual(classify_item("S202", "C1", missing), "sparse_baseline")
        self.assertEqual(classify_item("G204", "C1", missing), "unavailable_observation")

    def test_facility_and_population_substitution_notes_do_not_invent_observations(self):
        items = {
            "C4": result("C4"),
            "D3": result("D3", 2, value={"requested_population": "상주", "population": "유동"}),
        }
        before = copy.deepcopy(items)
        notes = coverage_notes("G204", items)
        self.assertTrue(any("시설 부재로 판단하지 않음" in note for note in notes))
        self.assertTrue(any("대체 자료" in note for note in notes))
        self.assertEqual(items, before)

    def test_all_six_unsupported_industries_keep_lifecycle_unknown(self):
        for code in INDUSTRIES_WITHOUT_SEOUL:
            with self.subTest(code=code):
                items = {name: result(name, 4) if name != "L" else result(name) for name in WEIGHTS}
                for name in ("S1", "S2", "S3", "S4"):
                    items[name] = result(name, reason="서울 대응 업종 없음")
                before = copy.deepcopy(items)
                row = summarize(code, items, "해당 없음")
                self.assertEqual(row["lower"], 60)
                self.assertEqual(row["coverage"], 0.6)
                self.assertEqual(row["badge"], "보류")
                self.assertEqual(items, before)
                self.assertTrue(
                    any("대응 업종이 없어" in t for t in row["confirmation_conditions"])
                )

    def test_complete_new_evidence_does_not_receive_unsupported_warning(self):
        items = {name: result(name, 4) for name in WEIGHTS}
        row = summarize("M107", items, "해당 없음")
        self.assertEqual(row["badge"], "추천")
        self.assertFalse(any("대응 업종이 없어" in t for t in row["confirmation_conditions"]))

    def test_explanatory_notes_do_not_demote_a_qualified_badge(self):
        items = {name: result(name, 4) for name in WEIGHTS}
        items["C1"] = result("C1", 2, agglomeration="무관")
        before = copy.deepcopy(items)
        row = summarize("N110", items, "해당 없음")
        self.assertEqual(row["lower"], 92.5)
        self.assertEqual(row["coverage"], 1)
        self.assertEqual(row["badge"], "추천")
        self.assertTrue(any("현장 경쟁 관측값이 아님" in t for t in row["confirmation_conditions"]))
        self.assertEqual(items, before)


if __name__ == "__main__":
    unittest.main()
