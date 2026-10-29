"""심사위원 시험 채점과 요약 보고를 검증합니다."""

import asyncio
import contextlib
import csv
import dataclasses
import io
import json
import tempfile
import unittest
from pathlib import Path

from examiner_eval import cli, runner
from examiner_eval.cases import Case, Seed, load_cases
from examiner_eval.score import score_case, summarize, write_report
from tests.test_examiner_eval_runner import make_store

CANDIDATES = {"A": {"fa1", "fa2", "fa3"}, "B": {"fb1", "fb2"}, "C": {"fc1"}}


def issue(code, kind, facts, issue_id="examiner:x"):
    return {
        "issue_id": issue_id,
        "industry_code": code,
        "target": "claim",
        "kind": kind,
        "comment": "확인",
        "fact_ids": list(facts),
        "suggested_check": "확인",
    }


def result(case_id="c1", issues=(), variant="V2", repeat=1, status="completed", **extra):
    base = dict(
        case_id=case_id,
        variant=variant,
        repeat=repeat,
        status=status,
        error_code=None if status == "completed" else "BUDGET_EXCEEDED",
        verdict="conditional",
        issues=list(issues),
        end_event={"rejections": 0},
        calls=2,
        input_tokens=100,
        output_tokens=10,
        elapsed_ms=1000,
        model="m",
        packet_chars=500,
        omitted_fact_ids=1,
    )
    return runner.CaseResult(**{**base, **extra})


def seeded(seeds, case_id="c1", split="tune"):
    return Case(case_id, "r1", split, "seeded", {"top5": []}, tuple(seeds))


E1 = Seed("E1", "A", "reasons_segments", "missing_evidence", ("fa1", "fa2"), None)
E2 = Seed("E2", "B", "reasons_segments", "scope_mismatch", ("fb1",), "fb2")
E3 = Seed("E3", "C", "risks_segments", "scope_mismatch", ("fc1",), "fa3")

TEXT = {"type": "text", "text": "문장"}
FACT = {"type": "fact", "fact_id": "fa1", "format": "text"}


def candidate(code, reasons, risks=()):
    return {"industry_code": code, "reasons_segments": list(reasons), "risks_segments": list(risks)}


def real_case(unsupported, supported=0):
    top5 = [candidate(f"U{i}", [TEXT]) for i in range(unsupported)]
    top5 += [candidate(f"S{i}", [TEXT, FACT]) for i in range(supported)]
    return Case("real1", "r1", "tune", "real", {"top5": top5}, ())


def clean_case(case_id="c1"):
    return Case(case_id, "r1", "tune", "clean", {"top5": []}, ())


class ScoreCaseTests(unittest.TestCase):
    def test_found_and_exact_for_each_kind(self):
        issues = [
            issue("A", "missing_evidence", ["fa2"]),
            issue("B", "scope_mismatch", ["fb2"]),
            issue("C", "scope_mismatch", ["fc1"]),
        ]
        score = score_case(seeded([E1, E2, E3]), result(issues=issues), CANDIDATES)
        self.assertEqual(score.found, {"E1": True, "E2": True, "E3": True})
        self.assertEqual(score.exact, {"E1": True, "E2": True, "E3": False})
        self.assertEqual(score.false_positives, 0)
        self.assertEqual(score.denominator, 3)

    def test_issue_without_code_matched_by_fact(self):
        issues = [issue(None, "missing_evidence", ["fa1"]), issue(None, "scope_mismatch", ["fb2"])]
        score = score_case(seeded([E1, E2]), result(issues=issues), CANDIDATES)
        self.assertEqual(score.found, {"E1": True, "E2": True})
        self.assertEqual(score.false_positives, 0)

    def test_issue_without_code_and_unknown_fact_is_false_positive(self):
        issues = [issue(None, "missing_evidence", ["zz"])]
        score = score_case(seeded([E1]), result(issues=issues), CANDIDATES)
        self.assertEqual(score.found, {"E1": False})
        self.assertEqual(score.false_positives, 1)

    def test_several_issues_on_one_seed_are_not_false_positives(self):
        issues = [issue("A", "missing_evidence", ["fa1"]), issue("A", "missing_evidence", ["fa3"])]
        score = score_case(seeded([E1]), result(issues=issues), CANDIDATES)
        self.assertEqual(score.false_positives, 0)
        self.assertTrue(score.found["E1"])

    def test_wrong_candidate_is_false_positive(self):
        issues = [issue("B", "missing_evidence", ["fa1"]), issue("A", "scope_mismatch", ["fa1"])]
        score = score_case(seeded([E1]), result(issues=issues), CANDIDATES)
        self.assertEqual(score.found, {"E1": False})
        self.assertEqual(score.false_positives, 2)

    def test_clean_case_counts_all_scope_kinds_as_false_positive(self):
        issues = [
            issue("A", "missing_evidence", ["fa1"]),
            issue("B", "scope_mismatch", ["fb1"]),
            issue("C", "factual_error", ["fc1"]),
        ]
        score = score_case(clean_case(), result(issues=issues), CANDIDATES)
        self.assertEqual(score.false_positives, 3)
        self.assertEqual(score.found, {})
        self.assertEqual(score.denominator, 0)

    def test_action_condition_is_other_not_false_positive(self):
        issues = [issue("A", "action_condition", ["fa1"]), issue("A", "duplicate_score", ["fa1"])]
        score = score_case(clean_case(), result(issues=issues), CANDIDATES)
        self.assertEqual(score.false_positives, 0)
        self.assertEqual(score.other_issues, 2)

    def test_real_case_denominator_capped_at_four(self):
        issues = [issue(f"U{i}", "missing_evidence", ["fa1"]) for i in range(5)]
        score = score_case(real_case(6, 1), result("real1", issues), CANDIDATES)
        self.assertEqual(score.denominator, 4)
        self.assertEqual(sum(score.found.values()), 5)
        self.assertEqual(set(score.found), {f"E1:U{i}" for i in range(6)})
        self.assertEqual(score.exact, {})
        self.assertEqual(score.false_positives, 0)

    def test_real_case_denominator_is_candidate_count_when_small(self):
        score = score_case(real_case(2, 3), result("real1"), CANDIDATES)
        self.assertEqual(score.denominator, 2)
        self.assertEqual(score.found, {"E1:U0": False, "E1:U1": False})

    def test_failed_counts_as_not_found(self):
        failed = result(status="failed", issues=[], end_event={})
        score = score_case(seeded([E1, E2]), failed, CANDIDATES)
        self.assertTrue(score.failed)
        self.assertEqual(score.found, {"E1": False, "E2": False})
        self.assertEqual(score.exact, {"E1": False, "E2": False})
        self.assertFalse(score.first_rejected)

    def test_first_rejected_reads_rejections_and_calls_come_from_result(self):
        rejected = result(end_event={"rejections": 1, "model_calls": 3}, calls=2)
        score = score_case(seeded([E1]), rejected, CANDIDATES)
        self.assertTrue(score.first_rejected)
        self.assertEqual(score.calls, 2)


def make_scores(rows):
    scores = []
    for index, (repeat, hit) in enumerate(rows):
        case = seeded([E1], case_id=f"c{index}")
        issues = [issue("A", "missing_evidence", ["fa1"])] if hit else []
        scores.append(score_case(case, result(case.case_id, issues, repeat=repeat), CANDIDATES))
    return scores


class SummaryTests(unittest.TestCase):
    def row(self, rows, metric, variant="V2", split="tune"):
        found = [
            r for r in rows if (r["variant"], r["split"], r["metric"]) == (variant, split, metric)
        ]
        self.assertEqual(len(found), 1, metric)
        return found[0]

    def test_summary_min_max_across_repeats(self):
        rows = summarize(make_scores([(1, True), (1, True), (2, False), (2, True)]))
        found = self.row(rows, "E1_found")
        self.assertEqual((found["mean"], found["min"], found["max"]), (0.75, 0.5, 1.0))
        self.assertEqual(found["n"], 4)
        self.assertEqual(self.row(rows, "calls")["mean"], 2)

    def test_denominator_is_cases_that_have_the_kind(self):
        rows = summarize(make_scores([(1, True)]))
        self.assertEqual(self.row(rows, "E1_found")["n"], 1)
        self.assertFalse([r for r in rows if r["metric"] == "E2_found"])

    def test_false_positive_means_split_by_source(self):
        bad = result("k1", [issue("A", "factual_error", ["fa1"])])
        scores = [
            score_case(clean_case("k1"), bad, CANDIDATES),
            score_case(clean_case("k2"), result("k2"), CANDIDATES),
        ]
        rows = summarize(scores)
        self.assertEqual(self.row(rows, "clean_false_positives")["mean"], 0.5)
        self.assertFalse([r for r in rows if r["metric"] == "seeded_false_positives"])

    def test_clean_false_positives_also_reported_without_failed_cases(self):
        bad = result("k1", [issue("A", "factual_error", ["fa1"])])
        scores = [
            score_case(clean_case("k1"), bad, CANDIDATES),
            score_case(clean_case("k2"), result("k2", status="failed", end_event={}), CANDIDATES),
        ]
        rows = summarize(scores)
        self.assertEqual(self.row(rows, "clean_false_positives")["mean"], 0.5)
        done = self.row(rows, "clean_false_positives_done")
        self.assertEqual((done["mean"], done["n"]), (1.0, 1))

    def test_real_recall_caps_and_skips_zero_denominator(self):
        issues = [issue(f"U{i}", "missing_evidence", ["fa1"]) for i in range(5)]
        scores = [
            score_case(real_case(6), result("real1", issues), CANDIDATES),
            score_case(real_case(0, 2), result("real1"), CANDIDATES),
        ]
        row = self.row(summarize(scores), "real_recall")
        self.assertEqual((row["mean"], row["n"]), (1.0, 1))

    def test_groups_by_variant_and_split(self):
        case = seeded([E1], split="test")
        scores = [
            score_case(case, result("c1", variant="V0"), CANDIDATES),
            score_case(case, result("c1", variant="V1"), CANDIDATES),
        ]
        keys = {(r["variant"], r["split"]) for r in summarize(scores)}
        self.assertEqual(keys, {("V0", "test"), ("V1", "test")})


def tool_message(call_id, payload):
    return {"role": "tool", "tool_call_id": call_id, "content": json.dumps(payload)}


def rejection(reason):
    return {
        "status": "error",
        "error": {"code": "INVALID_REFERENCE"},
        "data": {"accepted": [], "rejected": [{"issue_id": "i1", "reason": reason}]},
    }


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def sample(self):
        case = seeded([E1])
        results = [
            result("c1", [issue("A", "missing_evidence", ["fa1"])], variant="V0"),
            result("c1", [], variant="V1", status="failed", end_event={}),
        ]
        return results, [score_case(case, r, CANDIDATES) for r in results]

    def read_csv(self, path):
        raw = path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))

    def test_write_report_files(self):
        results, scores = self.sample()
        out = self.folder / "report"
        write_report(results, scores, out, rejections={("V0", "tune"): {"숫자 금지": 2}})
        summary = (out / "요약.md").read_text(encoding="utf-8")
        for needle in ("V0", "V1", "읽는 법", "BUDGET_EXCEEDED", "숫자 금지", "tune"):
            self.assertIn(needle, summary)
        self.assertIn("100.0% (100.0%–100.0%)", summary)
        self.assertIn("기록 없음", summary)
        rows = self.read_csv(out / "요약.csv")
        self.assertIn("E1_found", {r["metric"] for r in rows})
        self.assertEqual(len(self.read_csv(out / "사례별.csv")), 2)

    def test_write_report_without_recordings(self):
        results, scores = self.sample()
        write_report(results, scores, self.folder, rejections=None)
        self.assertIn("기록 없음", (self.folder / "요약.md").read_text(encoding="utf-8"))

    def test_write_report_never_overwrites(self):
        results, scores = self.sample()
        (self.folder / "요약.csv").write_text("keep", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            write_report(results, scores, self.folder)
        self.assertEqual((self.folder / "요약.csv").read_text(encoding="utf-8"), "keep")
        self.assertFalse((self.folder / "요약.md").exists())


class CliReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        src = asyncio.run(make_store(self.folder))
        self.db = self.folder / "copy.sqlite3"
        self.out = self.folder / "out"
        self.cases = self.out / "cases.json"
        self.call("build", "--src", src, "--db", self.db, "--out", self.out)
        self.run_dir = self.folder / "run_v2"
        self.run_dir.mkdir()
        self.case = load_cases(self.cases)[0]

    def tearDown(self):
        self.temp.cleanup()

    def call(self, *argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main([str(a) for a in argv])
        return code, stdout.getvalue(), stderr.getvalue()

    def write_run(self, run_dir, case_id, variant="V2", with_calls=True):
        header = {"type": "header", "variant": variant, "split": "all", "mode": "fake"}
        runner.append_row(run_dir / runner.RESULTS, header | {"model": "fake"})
        row = dataclasses.asdict(result(case_id, variant=variant, model="fake"))
        runner.append_row(run_dir / runner.RESULTS, {"type": "result", **row})
        if with_calls:
            calls = run_dir / "calls"
            calls.mkdir(exist_ok=True)
            name = runner.re.sub(r"[^0-9A-Za-z_-]", "_", case_id) + f"__{variant}__1.json"
            entry = {"role": "examiner", "messages": [tool_message("t1", rejection("측정 숫자"))]}
            (calls / name).write_text(json.dumps([entry, entry]), encoding="utf-8")

    def report_args(self, out, *runs):
        return ("report", "--db", self.db, "--cases", self.cases, "--runs", *runs, "--out", out)

    def test_report_writes_files_and_refuses_overwrite(self):
        self.write_run(self.run_dir, self.case.case_id)
        out = self.folder / "rep"
        code, _, err = self.call(*self.report_args(out, self.run_dir))
        self.assertEqual((code, err), (0, ""))
        for name in ("요약.md", "요약.csv", "사례별.csv"):
            self.assertTrue((out / name).exists())
        self.assertIn("측정 숫자", (out / "요약.md").read_text(encoding="utf-8"))
        code, _, err = self.call(*self.report_args(out, self.run_dir))
        self.assertEqual(code, 2)
        self.assertTrue(err)

    def test_report_counts_rejections_kept_in_results(self):
        header = {"type": "header", "variant": "V2", "split": "all", "mode": "fake"}
        runner.append_row(self.run_dir / runner.RESULTS, header | {"model": "fake"})
        row = dataclasses.asdict(
            result(self.case.case_id, model="fake", rejected_reasons=["마지막 거절", "마지막 거절"])
        )
        runner.append_row(self.run_dir / runner.RESULTS, {"type": "result", **row})
        out = self.folder / "rep"
        self.assertEqual(self.call(*self.report_args(out, self.run_dir))[0], 0)
        summary = (out / "요약.md").read_text(encoding="utf-8")
        self.assertIn("마지막 거절", summary)
        self.assertNotIn("기록 없음", summary)

    def test_report_without_recordings_says_so(self):
        self.write_run(self.run_dir, self.case.case_id, with_calls=False)
        out = self.folder / "rep"
        self.assertEqual(self.call(*self.report_args(out, self.run_dir))[0], 0)
        self.assertIn("기록 없음", (out / "요약.md").read_text(encoding="utf-8"))

    def test_report_refuses_missing_results_and_unknown_case(self):
        out = self.folder / "rep"
        self.assertEqual(self.call(*self.report_args(out, self.run_dir))[0], 2)
        self.write_run(self.run_dir, "없는사례")
        self.assertEqual(self.call(*self.report_args(out, self.run_dir))[0], 2)
        self.assertFalse((out / "요약.md").exists())

    def test_report_refuses_duplicate_results(self):
        self.write_run(self.run_dir, self.case.case_id)
        other = self.folder / "run_again"
        other.mkdir()
        self.write_run(other, self.case.case_id)
        out = self.folder / "rep"
        self.assertEqual(self.call(*self.report_args(out, self.run_dir, other))[0], 2)


if __name__ == "__main__":
    unittest.main()
