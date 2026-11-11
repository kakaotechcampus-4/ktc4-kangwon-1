import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.measure_consistency import compare_runs, main, role_models, summarize_run


def result(top5, grades, badges=None, evaluators=None, resolutions=None):
    return {
        "top5": [
            {"industry_code": code, "badge": (badges or {}).get(code, "추천")} for code in top5
        ],
        "L_records": [
            {
                "industry_code": code,
                "status": "unknown" if grade is None else "observed",
                "grade": grade,
            }
            for code, grade in grades.items()
        ],
        "evaluator_reviews": [
            {"actor": actor, "status": status, "verdict": "agree", "issues": [{}]}
            for actor, status in (
                evaluators
                or {
                    "examiner": "completed",
                    "customer": "completed",
                    "founder": "completed",
                    "landlord_advocate": "completed",
                }
            ).items()
        ],
        "review_resolutions": [{"disposition": d} for d in (resolutions or [])],
        "review_completeness": 1.0,
    }


BUDGET = {
    "active_seconds": 90.5,
    "calls": [
        {"role": "decision", "input_tokens": 1000, "output_tokens": 100},
        {"role": "decision", "input_tokens": 2000, "output_tokens": 200},
        {"role": "examiner", "input_tokens": 500, "output_tokens": 50},
    ],
}


class SummarizeRunTests(unittest.TestCase):
    def test_counts_calls_tokens_and_keeps_ranked_choices(self):
        summary = summarize_run(
            "completed",
            result(["A1", "B2"], {"A1": 3, "B2": None}, resolutions=["accepted", "rejected"]),
            BUDGET,
            120.0,
        )
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["seconds"], 120.0)
        self.assertEqual(summary["calls"], 3)
        self.assertEqual(summary["calls_by_role"], {"decision": 2, "examiner": 1})
        self.assertEqual(summary["input_tokens"], 3500)
        self.assertEqual(summary["output_tokens"], 350)
        self.assertEqual(summary["top5"], ["A1", "B2"])
        self.assertEqual(summary["L"], {"A1": 3, "B2": None})
        self.assertEqual(summary["evaluators_completed"], 4)
        self.assertEqual(summary["issues"], 4)
        self.assertEqual(summary["resolutions"], {"accepted": 1, "rejected": 1})

    def test_failed_run_has_no_choices(self):
        summary = summarize_run("failed", None, {"calls": []}, 3.0)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["top5"], [])
        self.assertEqual(summary["L"], {})
        self.assertEqual(summary["calls"], 0)


class CompareRunsTests(unittest.TestCase):
    def run_summary(self, top5, grades):
        return summarize_run("completed", result(top5, grades), BUDGET, 100.0)

    def test_identical_runs_are_fully_consistent(self):
        runs = [self.run_summary(["A", "B", "C"], {"A": 3, "B": 2, "C": None})] * 3
        report = compare_runs(runs)
        self.assertTrue(report["top5_identical"])
        self.assertTrue(report["top5_same_set"])
        self.assertTrue(report["top1_same"])
        self.assertEqual(report["top5_jaccard_mean"], 1.0)
        self.assertEqual(report["L_status_agree_share"], 1.0)
        self.assertEqual(report["L_max_grade_diff"], 0)
        self.assertEqual(report["L_grade_diff_le1_share"], 1.0)

    def test_measures_rank_and_grade_drift(self):
        runs = [
            self.run_summary(["A", "B", "C"], {"A": 4, "B": 2, "C": None}),
            self.run_summary(["B", "A", "C"], {"A": 2, "B": 2, "C": 1}),
            self.run_summary(["A", "B", "D"], {"A": 3, "B": 2, "C": None}),
        ]
        report = compare_runs(runs)
        self.assertFalse(report["top5_identical"])
        self.assertFalse(report["top5_same_set"])
        self.assertFalse(report["top1_same"])
        self.assertAlmostEqual(report["top5_jaccard_mean"], (1 + 0.5 + 0.5) / 3)
        self.assertAlmostEqual(report["L_status_agree_share"], 2 / 3)
        self.assertEqual(report["L_max_grade_diff"], 2)
        self.assertAlmostEqual(report["L_grade_diff_le1_share"], 1 / 2)

    def test_counts_only_completed_runs(self):
        runs = [
            self.run_summary(["A"], {"A": 3}),
            summarize_run("failed", None, {"calls": []}, 1.0),
        ]
        report = compare_runs(runs)
        self.assertEqual(report["completed_runs"], 1)
        self.assertEqual(report["total_runs"], 2)


class MockRunTests(unittest.TestCase):
    def test_mock_run_writes_summary_without_paid_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            sites = Path(tmp) / "sites.json"
            sites.write_text(
                json.dumps([{"label": "시험", "address": "시험", "floor": "1층"}]),
                encoding="utf-8",
            )
            out = Path(tmp) / "out"
            code = main(["--sites", str(sites), "--runs", "2", "--out", str(out), "--mock"])
            self.assertEqual(code, 0)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["mode"], "mock")
            self.assertEqual(summary["sites"][0]["label"], "시험")
            comparison = summary["sites"][0]["comparison"]
            self.assertEqual(comparison["total_runs"], 2)
            self.assertEqual(comparison["completed_runs"], 2)
            self.assertTrue(comparison["top5_identical"])

    def test_real_summary_names_role_models_without_keys(self):
        env = {
            "DECISION_LLM_MODEL": "decision-model",
            "EVALUATOR_LLM_MODEL": "evaluator-model",
            "ADVISOR_LLM_MODEL": "advisor-model",
            "DECISION_LLM_API_KEY": "secret-key",
        }
        with mock.patch.dict(os.environ, env):
            models = role_models()
        self.assertEqual(
            models,
            {
                "decision": "decision-model",
                "evaluator": "evaluator-model",
                "advisor": "advisor-model",
            },
        )
        self.assertNotIn("secret-key", json.dumps(models))

    def test_paid_run_needs_real_flag_and_call_cap(self):
        with self.assertRaises(SystemExit):
            main(["--sites", "x.json", "--out", "o"])
        with self.assertRaises(SystemExit):
            main(["--sites", "x.json", "--out", "o", "--real"])


if __name__ == "__main__":
    unittest.main()
