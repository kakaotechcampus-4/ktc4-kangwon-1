"""확정값의 표기 보완이 미확인 숫자나 잘못된 근거를 통과시키지 않는지 확인합니다."""

import unittest
from copy import deepcopy

from app.domain.report_input import normalize_report_input, numeric_text_paths

FLOOR = "f_00000000-0000-4000-8000-000000000001"
AREA = "f_00000000-0000-4000-8000-000000000002"
LITERALS = {"1층": FLOOR, "41㎡": AREA}


def arguments(text):
    return {"phase": "draft", "report": {"summary_segments": [{"type": "text", "text": text}]}}


class ReportInputTests(unittest.TestCase):
    def test_exact_confirmed_values_become_references_without_mutating_input(self):
        original = arguments("확인된 1층 공간은 41㎡입니다.")
        before = deepcopy(original)
        normalized, warnings = normalize_report_input(original, LITERALS)
        segments = normalized["report"]["summary_segments"]
        self.assertEqual([s["fact_id"] for s in segments if s["type"] == "fact"], [FLOOR, AREA])
        self.assertEqual(numeric_text_paths(normalized["report"]), [])
        self.assertEqual(segments[0]["text"], "확인된 ")
        self.assertEqual(segments[2]["text"], " 공간은 ")
        self.assertEqual(original, before)
        self.assertTrue(warnings)

    def test_different_values_signs_and_units_remain_unverified(self):
        for text in (
            "11층",
            "지하 1층",
            "B1층",
            "-1층",
            "+1층",
            "- 1층",
            "+ 1층",
            "지하 - 1층",
            "− 1층",
            "141㎡",
            "41.5㎡",
            "1,041㎡",
            "41평",
            "매출 41만원",
        ):
            with self.subTest(text=text):
                original = arguments(text)
                normalized, warnings = normalize_report_input(original, LITERALS)
                self.assertEqual(normalized, original)
                self.assertEqual(warnings, [])
                self.assertEqual(
                    numeric_text_paths(normalized["report"]), ["report.summary_segments.0"]
                )

    def test_no_confirmed_value_means_no_numeric_repair(self):
        original = arguments("1층 공간은 41㎡입니다.")
        normalized, warnings = normalize_report_input(original, {})
        self.assertEqual(normalized, original)
        self.assertEqual(warnings, [])

    def test_whitespace_does_not_change_the_confirmed_number_or_unit(self):
        normalized, _ = normalize_report_input(arguments("1 층, 41 ㎡"), LITERALS)
        self.assertEqual(
            [s["fact_id"] for s in normalized["report"]["summary_segments"] if s["type"] == "fact"],
            [FLOOR, AREA],
        )

    def test_existing_valid_segments_are_preserved(self):
        original = {
            "phase": "final",
            "report": {"summary_segments": [{"type": "fact", "fact_id": AREA, "format": "text"}]},
            "review_resolutions": [],
        }
        normalized, warnings = normalize_report_input(original, LITERALS)
        self.assertEqual(normalized, original)
        self.assertEqual(warnings, [])

    def test_only_missing_format_is_filled_without_overwriting_explicit_format(self):
        original = {
            "phase": "draft",
            "report": {
                "summary_segments": [
                    {"type": "fact", "fact_id": AREA},
                    {"type": "fact", "fact_id": FLOOR, "format": "invalid"},
                ]
            },
        }
        normalized, warnings = normalize_report_input(original, {})
        first, second = normalized["report"]["summary_segments"]
        self.assertEqual(first["format"], "text")
        self.assertEqual(second["format"], "invalid")
        self.assertTrue(warnings)

    def test_extra_text_fields_are_not_silently_removed(self):
        original = arguments("1층")
        original["report"]["summary_segments"][0]["unexpected"] = True
        normalized, _ = normalize_report_input(original, LITERALS)
        self.assertEqual(normalized, original)

    def test_candidate_and_excluded_sections_use_the_same_rules(self):
        original = {
            "phase": "draft",
            "report": {
                "candidates": [
                    {"industry_code": "G203", "reasons_segments": [{"type": "text", "text": "1층"}]}
                ],
                "excluded_candidates": [
                    {"industry_code": "G208", "risks_segments": [{"type": "fact", "fact_id": AREA}]}
                ],
            },
        }
        normalized, _ = normalize_report_input(original, LITERALS)
        report = normalized["report"]
        self.assertEqual(report["candidates"][0]["reasons_segments"][0]["fact_id"], FLOOR)
        self.assertEqual(report["excluded_candidates"][0]["risks_segments"][0]["format"], "text")

    def test_numeric_error_paths_identify_nested_fields_and_do_not_echo_text(self):
        report = {
            "summary_segments": [{"type": "text", "text": "매출 999만원"}],
            "candidates": [
                {"industry_code": "G203", "risks_segments": [{"type": "text", "text": "3층"}]}
            ],
        }
        self.assertEqual(
            numeric_text_paths(report),
            ["report.summary_segments.0", "report.candidates.0.risks_segments.0"],
        )
