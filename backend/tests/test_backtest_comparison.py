"""미적용 보정·결측 유지·자료 부족 후보 차단을 운영 채점과 독립적으로 확인합니다."""

import copy
import unittest

from app.agentic.scoring import WEIGHTS, result, summarize
from backtest.comparison import code_summary, compare_rankings


def row(code="I201", grade=4):
    items = {name: result(name, grade) if name != "L" else result(name) for name in WEIGHTS}
    return summarize(code, items, "해당 없음")


class ComparisonTests(unittest.TestCase):
    def test_equal_fit_is_comparable_despite_different_applicable_weights(self):
        full, reduced = row(grade=2), row("G204", grade=2)
        for name in ("D2", "C4"):
            reduced["items"][name] = result(name, status="n.a.")
        full_summary, reduced_summary = code_summary(full), code_summary(reduced)
        self.assertGreater(full_summary["code_points"], reduced_summary["code_points"])
        self.assertEqual(full_summary["normalized_lower"], reduced_summary["normalized_lower"])
        self.assertEqual(full_summary["normalized_lower"], 45)

    def test_unknown_keeps_its_weight_and_differs_from_observed_zero(self):
        unknown, zero, na = row(), row(), row()
        unknown["items"]["D2"] = result("D2")
        zero["items"]["D2"] = result("D2", 0)
        na["items"]["D2"] = result("D2", status="n.a.")
        unknown_summary, zero_summary, na_summary = map(code_summary, (unknown, zero, na))
        self.assertEqual(unknown_summary["normalized_lower"], 80)
        self.assertEqual(zero_summary["normalized_lower"], 80)
        self.assertEqual(na_summary["normalized_lower"], 90)
        self.assertLess(unknown_summary["coverage"], zero_summary["coverage"])
        self.assertEqual(unknown_summary["unknown_weight"], 10)
        self.assertEqual(zero_summary["unknown_weight"], 0)

    def test_a_single_perfect_item_does_not_qualify_for_guarded_candidates(self):
        thin, complete = row("G204"), row("I201", grade=3)
        for name in WEIGHTS:
            if name not in {"D1", "L"}:
                thin["items"][name] = result(name, status="n.a.")
        comparison = compare_rankings([thin, complete])
        self.assertEqual(comparison["top5"]["applicable"], ["G204", "I201"])
        self.assertEqual(comparison["top5"]["guarded"], ["I201"])

    def test_no_data_never_qualifies_and_no_applicable_items_have_no_ratio(self):
        unknown, na = row("G204"), row("I201")
        for name in WEIGHTS:
            if name != "L":
                unknown["items"][name] = result(name)
                na["items"][name] = result(name, status="n.a.")
        self.assertEqual(code_summary(unknown)["coverage"], 0)
        self.assertIsNone(code_summary(na)["normalized_lower"])
        self.assertEqual(compare_rankings([unknown, na])["top5"]["guarded"], [])

    def test_regulation_and_space_exclusions_apply_to_every_method(self):
        prohibited, excluded, allowed = row("G204"), row("G205"), row(grade=2)
        prohibited["regulation"] = "금지"
        excluded["space"] = {"excluded": True, "adjustment": 0}
        comparison = compare_rankings([prohibited, excluded, allowed])
        for candidates in comparison["top5"].values():
            self.assertEqual(candidates, ["I201"])

    def test_ties_return_exactly_five_and_do_not_mutate_original_scores(self):
        rows = [row(code) for code in ("G202", "G203", "G204", "G205", "G208", "G209")]
        before = copy.deepcopy(rows)
        comparison = compare_rankings(rows)
        for candidates in comparison["top5"].values():
            self.assertEqual(len(candidates), 5)
            self.assertNotIn("G209", candidates)
        self.assertEqual(rows, before)

    def test_unknown_points_and_non_finite_observations_are_rejected(self):
        for status, points in (("unknown", 0), ("n.a.", 10), ("observed", float("nan"))):
            with self.subTest(status=status):
                candidate = row()
                candidate["items"]["D2"].update(status=status, points=points)
                with self.assertRaises(ValueError):
                    code_summary(candidate)

    def test_llm_reviewed_scores_cannot_be_mislabeled_as_code_only(self):
        candidate = row()
        candidate["items"]["L"] = result("L", 0)
        with self.assertRaisesRegex(ValueError, "L 판단 전"):
            compare_rankings([candidate])

    def test_normalization_preserves_the_service_coverage_tie_breaker(self):
        full = row("I201", grade=2)
        items = row("G204", grade=2)["items"]
        for name in ("D2", "C4"):
            items[name] = result(name, status="n.a.")
        reduced = summarize("G204", items, "해당 없음")
        comparison = compare_rankings([reduced, full])
        self.assertEqual(comparison["top5"]["applicable"], ["I201", "G204"])


if __name__ == "__main__":
    unittest.main()
