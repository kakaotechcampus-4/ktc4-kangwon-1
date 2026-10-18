import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.industries.catalog import INDUSTRIES
from backtest.full import (
    MARKER,
    RESULT,
    assess,
    compare,
    main,
    run_full,
    run_health,
    snapshot_rows,
)
from backtest.run import file_sha256

CODES = list(INDUSTRIES)[:3]


def rows_with(lowers, l_points=None):
    out = []
    for code, lower in zip(CODES, lowers, strict=True):
        items = {name: {"status": "unknown", "grade": None, "points": None} for name in ("C4", "L")}
        if l_points and code in l_points:
            items["L"] = {"status": "observed", "grade": 4, "points": l_points[code]}
        out.append(
            {
                "code": code,
                "name": code,
                "items": items,
                "lower": lower,
                "coverage": 0.8,
                "regulation": "해당 없음",
            }
        )
    return out


def sample_row(number=1, code=CODES[2]):
    return {
        "업종코드": "SV001",
        "업종": INDUSTRIES[code],
        "그룹": "1",
        "순번": str(number),
        "상호": "가",
        "주소": "서울 마포구 와우산로 94",
    }


def write_calls(path):
    Path(path).write_text(json.dumps([{}, {}, {}]), encoding="utf-8")


class SnapshotTests(unittest.TestCase):
    def test_picks_first_unreviewed_and_last_reviewed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "requests.sqlite3"
            db = sqlite3.connect(path)
            db.execute(
                "CREATE TABLE score_snapshots "
                "(request_id, summary_json, L_review_state, created_at)"
            )
            db.executemany(
                "INSERT INTO score_snapshots VALUES (?,?,?,?)",
                [
                    ("r", json.dumps([{"code": "first"}]), "unreviewed", "1"),
                    ("r", json.dumps([{"code": "later"}]), "unreviewed", "2"),
                    ("r", json.dumps([{"code": "old"}]), "reviewed", "3"),
                    ("r", json.dumps([{"code": "final"}]), "reviewed", "4"),
                ],
            )
            db.commit()
            db.close()
            self.assertEqual(snapshot_rows(path, "r", reviewed=False), [{"code": "first"}])
            self.assertEqual(snapshot_rows(path, "r", reviewed=True), [{"code": "final"}])
            self.assertIsNone(snapshot_rows(path, "none", reviewed=True))


class CompareTests(unittest.TestCase):
    def test_ranks_before_and_after_l(self):
        code_rows = rows_with([60, 50, 40])
        final_rows = rows_with([60, 50, 65], {CODES[2]: 10.0})
        result = compare("SV001-1", CODES[2], code_rows, final_rows, 27)
        self.assertEqual(result["코드 순위"], 3)
        self.assertEqual(result["최종 순위"], 1)
        self.assertEqual(result["호출 수"], 27)
        self.assertEqual(result["상위5 겹침"], 3)


class RunFullTests(unittest.TestCase):
    def test_records_calls_and_ranks(self):
        async def analyze(
            address, *, db_path, local_data_path, request_id, recording_path, allow_questions
        ):
            write_calls(recording_path)
            return SimpleNamespace(status="completed")

        def fake_rows(db_path, request_id, *, reviewed):
            return rows_with([60, 50, 65] if reviewed else [60, 50, 40])

        with (
            tempfile.TemporaryDirectory() as folder,
            patch("backtest.full.snapshot_rows", fake_rows),
        ):
            out = Path(folder)
            results, _ = asyncio.run(
                run_full(
                    [sample_row()],
                    out=out,
                    data_path=Path("x"),
                    requests_db=Path("y"),
                    analyze=analyze,
                )
            )
            saved = json.loads((out / RESULT).read_text(encoding="utf-8"))
        self.assertEqual(results[0]["상태"], "완료")
        self.assertEqual(results[0]["호출 수"], 3)
        self.assertEqual(saved[0]["최종 순위"], 1)

    def test_error_is_recorded(self):
        async def analyze(*args, **kwargs):
            raise RuntimeError("모델 오류")

        with tempfile.TemporaryDirectory() as folder:
            results, _ = asyncio.run(
                run_full(
                    [sample_row()],
                    out=Path(folder),
                    data_path=Path("x"),
                    requests_db=Path("y"),
                    analyze=analyze,
                )
            )
        self.assertEqual(results[0]["상태"], "오류")

    def test_done_rows_are_skipped(self):
        calls = []

        async def analyze(address, **kwargs):
            calls.append(address)
            raise RuntimeError("부르면 안 됨")

        done = [{"행": "SV001-1", "상태": "완료"}]
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(
                run_full(
                    [sample_row()],
                    out=Path(folder),
                    data_path=Path("x"),
                    requests_db=Path("y"),
                    analyze=analyze,
                    done=done,
                )
            )
        self.assertEqual(calls, [])


class MainTests(unittest.TestCase):
    def args(self, out, *extra):
        return [
            "--input",
            "a.csv",
            "--data",
            "d",
            "--baselines",
            "b",
            "--out",
            str(out),
            "--rows",
            "SV001-1",
            *extra,
        ]

    def test_requires_real_flag(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(SystemExit):
            main(self.args(Path(folder) / "new"))

    def test_refuses_more_than_max_rows(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(SystemExit):
            main(
                [
                    "--input",
                    "a.csv",
                    "--data",
                    "d",
                    "--baselines",
                    "b",
                    "--out",
                    str(Path(folder) / "new"),
                    "--rows",
                    ",".join(f"SV001-{n}" for n in range(1, 12)),
                    "--real",
                    "--max-calls",
                    "100",
                ]
            )

    def test_refuses_an_empty_model_key(self):
        with tempfile.TemporaryDirectory() as folder:
            sample = Path(folder) / "a.csv"
            sample.write_text(
                "업종코드,업종,그룹,순번,상호,주소\nSV001,"
                + INDUSTRIES[CODES[0]]
                + ",1,1,가,서울\n",
                encoding="utf-8-sig",
            )
            argv = [
                "--input",
                str(sample),
                "--data",
                "d",
                "--baselines",
                "b",
                "--out",
                str(Path(folder) / "new"),
                "--rows",
                "SV001-1",
                "--real",
                "--max-calls",
                "100",
            ]
            with (
                patch("backtest.full.load_environment"),
                patch.dict(os.environ, {"ELICE_API_KEY": ""}),
            ):
                self.assertEqual(main(argv), 1)


CLEAN = {
    "fallback": False,
    "fallback_reasons": [],
    "advisor_unavailable": False,
    "l_submitted": 51,
    "model_errors": {},
}

VERSIONS = [{"version_id": "v1", "file_hash": "aa"}, {"version_id": "v2", "file_hash": "bb"}]


def health(**changes):
    return {**CLEAN, **changes}


def state_with(limitations, records, advisor=False):
    return {
        "limitations": limitations,
        "L_records": records,
        "advisor_unavailable": advisor,
    }


def make_db(path, states):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE agentic_runs (request_id, state_json)")
    for request_id, state in states.items():
        db.execute("INSERT INTO agentic_runs VALUES (?,?)", (request_id, json.dumps(state)))
    db.commit()
    db.close()


def unsubmitted(code):
    return {
        "industry_code": code,
        "limitations": ["L 판단 미제출: 확인된 새 근거를 제출하지 않았습니다."],
    }


def submitted(code):
    return {"industry_code": code, "limitations": []}


def write_entries(path, entries):
    Path(path).write_text(json.dumps(entries), encoding="utf-8")


class RunHealthTests(unittest.TestCase):
    def test_reads_fallback_advisor_l_count_and_model_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "r.sqlite3"
            recording = Path(folder) / "c.json"
            records = {"A": submitted("A"), "B": unsubmitted("B"), "C": unsubmitted("C")}
            limits = ["다른 한계", "L 판단 미제출 업종 수: 2", "예산 도달", MARKER]
            make_db(db_path, {"r1": state_with(limits, records, advisor=True)})
            write_entries(
                recording,
                [
                    {"role": "decision", "error": None, "error_code": None},
                    {"role": "decision", "error": "x", "error_code": "LLM_CONNECTION_ERROR"},
                    {"role": "advisor", "error": None, "error_code": "LLM_OUTPUT_LIMIT"},
                    {"role": "advisor", "error": "y", "error_code": None},
                ],
            )
            result = run_health(db_path, "r1", recording)
        self.assertTrue(result["fallback"])
        self.assertEqual(result["fallback_reasons"], ["예산 도달"])
        self.assertTrue(result["advisor_unavailable"])
        self.assertEqual(result["l_submitted"], 1)
        self.assertEqual(result["model_errors"], {"decision": 1, "advisor": 2})

    def test_clean_run(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "r.sqlite3"
            recording = Path(folder) / "c.json"
            make_db(db_path, {"r1": state_with(["다른 한계"], {"A": submitted("A")})})
            write_entries(recording, [{"role": "decision", "error": None, "error_code": None}])
            result = run_health(db_path, "r1", recording)
        self.assertFalse(result["fallback"])
        self.assertEqual(result["fallback_reasons"], [])
        self.assertFalse(result["advisor_unavailable"])
        self.assertEqual(result["l_submitted"], 1)
        self.assertEqual(result["model_errors"], {})

    def test_missing_request_and_recording_give_empty_health(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "r.sqlite3"
            make_db(db_path, {})
            result = run_health(db_path, "none", Path(folder) / "none.json")
        self.assertFalse(result["fallback"])
        self.assertEqual(result["model_errors"], {})
        self.assertEqual(result["l_submitted"], 0)


class AssessTests(unittest.TestCase):
    def test_complete_only_without_fallback_and_errors(self):
        self.assertEqual(assess("완료", health(), 10), "완료")

    def test_fallback_is_substitute_finish(self):
        self.assertEqual(assess("완료", health(fallback=True), 10), "대체 마무리")

    def test_any_model_error_is_substitute_finish(self):
        self.assertEqual(assess("완료", health(model_errors={"advisor": 1}), 10), "대체 마무리")

    def test_more_than_half_errors_is_invalid(self):
        self.assertEqual(assess("완료", health(model_errors={"decision": 6}), 10), "무효")
        self.assertEqual(assess("완료", health(model_errors={"decision": 5}), 10), "대체 마무리")

    def test_error_and_no_score_stay(self):
        self.assertEqual(assess("오류", health(fallback=True), 10), "오류")
        self.assertEqual(assess("점수 없음", health(model_errors={"d": 9}), 10), "점수 없음")


def ok_analyzer(calls=3):
    async def analyze(address, *, recording_path, **kwargs):
        write_entries(recording_path, [{}] * calls)
        return SimpleNamespace(status="completed")

    return analyze


def fake_rows(db_path, request_id, *, reviewed):
    return rows_with([60, 50, 65] if reviewed else [60, 50, 40])


def run_rows_with(rows, folder, *, healths, analyze=None, **kwargs):
    queue = iter(healths)
    with (
        patch("backtest.full.snapshot_rows", fake_rows),
        patch("backtest.full.run_health", lambda *a: next(queue)),
    ):
        return asyncio.run(
            run_full(
                rows,
                out=Path(folder),
                data_path=Path("x"),
                requests_db=Path("y"),
                analyze=analyze or ok_analyzer(),
                **kwargs,
            )
        )


def numbered(count):
    return [sample_row(n) for n in range(1, count + 1)]


class HealthInRunTests(unittest.TestCase):
    def test_health_fields_and_status_are_attached(self):
        with tempfile.TemporaryDirectory() as folder:
            results, _ = run_rows_with(
                [sample_row()],
                folder,
                healths=[
                    health(
                        fallback=True,
                        fallback_reasons=["예산"],
                        l_submitted=7,
                        model_errors={"advisor": 1},
                    )
                ],
            )
        row = results[0]
        self.assertEqual(row["상태"], "대체 마무리")
        self.assertTrue(row["대체 마무리"])
        self.assertEqual(row["대체 마무리 사유"], ["예산"])
        self.assertFalse(row["자문 실패"])
        self.assertEqual(row["L 제출 업종 수"], 7)
        self.assertEqual(row["모델 오류 수"], {"advisor": 1})

    def test_resume_reruns_rows_that_are_not_complete(self):
        done = [
            {"행": "SV001-1", "상태": "대체 마무리"},
            {"행": "SV001-2", "상태": "완료"},
        ]
        with tempfile.TemporaryDirectory() as folder:
            results, _ = run_rows_with(numbered(2), folder, healths=[health()], done=done)
        self.assertEqual([r["행"] for r in results], ["SV001-2", "SV001-1"])
        self.assertEqual([r["상태"] for r in results], ["완료", "완료"])


class StopTests(unittest.TestCase):
    def failing(self):
        async def analyze(*args, **kwargs):
            raise RuntimeError("실패")

        return analyze

    def test_two_consecutive_bad_rows_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            results, stopped = run_rows_with(
                numbered(4), folder, healths=[health()] * 4, analyze=self.failing()
            )
        self.assertEqual(len(results), 2)
        self.assertEqual(stopped, "consecutive_errors")

    def test_a_good_row_resets_the_streak(self):
        calls = iter([True, False, True, False])

        async def analyze(address, *, recording_path, **kwargs):
            if next(calls):
                raise RuntimeError("실패")
            write_calls(recording_path)
            return SimpleNamespace(status="completed")

        with tempfile.TemporaryDirectory() as folder:
            results, stopped = run_rows_with(
                numbered(4), folder, healths=[health()] * 4, analyze=analyze
            )
        self.assertEqual(len(results), 4)
        self.assertIsNone(stopped)

    def test_model_error_in_first_row_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            results, stopped = run_rows_with(
                numbered(3), folder, healths=[health(model_errors={"decision": 1})] * 3
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(stopped, "first_row_model_error")

    def test_model_error_in_a_later_row_does_not_stop_alone(self):
        with tempfile.TemporaryDirectory() as folder:
            results, stopped = run_rows_with(
                numbered(3),
                folder,
                healths=[health(), health(model_errors={"decision": 1}), health()],
            )
        self.assertEqual(len(results), 3)
        self.assertIsNone(stopped)

    def test_consecutive_model_error_rows_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            results, stopped = run_rows_with(
                numbered(4),
                folder,
                healths=[health(), health(model_errors={"d": 1}), health(model_errors={"d": 1})],
            )
        self.assertEqual(len(results), 3)
        self.assertEqual(stopped, "consecutive_errors")

    def test_max_calls_stops_before_the_next_row(self):
        with tempfile.TemporaryDirectory() as folder:
            results, stopped = run_rows_with(
                numbered(5), folder, healths=[health()] * 5, max_calls=6
            )
        self.assertEqual(len(results), 2)
        self.assertEqual(stopped, "max_calls")

    def test_skipped_done_rows_do_not_count_toward_max_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            results, stopped = run_rows_with(
                numbered(2),
                folder,
                healths=[health()],
                max_calls=1,
                done=[{"행": "SV001-1", "상태": "완료", "호출 수": 50}],
            )
        self.assertEqual(len(results), 2)
        self.assertIsNone(stopped)


class FullMainTests(unittest.TestCase):
    def setup_files(self, folder):
        root = Path(folder)
        sample = root / "a.csv"
        sample.write_text(
            f"업종코드,업종,그룹,순번,상호,주소\nSV001,{INDUSTRIES[CODES[0]]},1,1,가,서울\n",
            encoding="utf-8-sig",
        )
        baseline = root / "baselines.json"
        baseline.write_text('{"quarter": "20234"}', encoding="utf-8")
        return sample, baseline

    def argv(self, sample, baseline, out, *extra):
        return [
            "--input",
            str(sample),
            "--data",
            "d",
            "--baselines",
            str(baseline),
            "--out",
            str(out),
            "--rows",
            "SV001-1",
            "--real",
            *extra,
        ]

    def run_main(self, argv, db, runner):
        with (
            patch("backtest.full.load_environment"),
            patch.dict(os.environ, {"ELICE_API_KEY": "k"}),
            patch("backtest.full.check_history_db", return_value=db),
            patch("backtest.full.load_baselines", return_value={"quarter": "20234"}),
            patch("backtest.full.swapped"),
            patch("backtest.full.run_full", runner),
        ):
            return main(argv)

    def test_real_requires_max_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            sample, baseline = self.setup_files(folder)
            with self.assertRaises(SystemExit):
                main(self.argv(sample, baseline, Path(folder) / "new"))

    def test_first_run_keeps_a_baseline_copy_and_records_stop(self):
        async def runner(*args, **kwargs):
            return [], "max_calls"

        with tempfile.TemporaryDirectory() as folder:
            sample, baseline = self.setup_files(folder)
            out = Path(folder) / "new"
            argv = self.argv(
                sample,
                baseline,
                out,
                "--max-calls",
                "5",
                "--requests",
                str(Path(folder) / "q" / "r.sqlite3"),
            )
            code = self.run_main(argv, {"versions": VERSIONS}, runner)
            kept = (out / "baseline.json").read_text(encoding="utf-8")
            meta = json.loads((out / "run_meta.json").read_text(encoding="utf-8"))
            original = baseline.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertEqual(kept, original)
        self.assertEqual(meta["runs"][0]["stopped"], "max_calls")

    def resume_case(self, *, kept_text, old_versions):
        async def runner(*args, **kwargs):
            raise AssertionError("분석 시작")

        with tempfile.TemporaryDirectory() as folder:
            sample, baseline = self.setup_files(folder)
            out = Path(folder) / "out"
            out.mkdir()
            (out / RESULT).write_text("[]", encoding="utf-8")
            (out / "baseline.json").write_text(kept_text or baseline.read_text(encoding="utf-8"))
            meta = {
                "runs": [
                    {
                        "baselines": {"sha256": file_sha256(out / "baseline.json")},
                        "data": {"versions": old_versions},
                    }
                ]
            }
            (out / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")
            argv = self.argv(
                sample,
                baseline,
                out,
                "--max-calls",
                "5",
                "--resume",
                "--requests",
                str(Path(folder) / "r.sqlite3"),
            )
            return self.run_main(argv, {"versions": VERSIONS}, runner)

    def test_resume_refuses_a_changed_baseline_before_any_analysis(self):
        self.assertEqual(self.resume_case(kept_text='{"quarter": "x"}', old_versions=VERSIONS), 1)

    def test_resume_refuses_changed_data_before_any_analysis(self):
        self.assertEqual(self.resume_case(kept_text=None, old_versions=VERSIONS[:1]), 1)


class ReassessTests(unittest.TestCase):
    def test_writes_a_new_file_without_touching_the_original(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            (out / "calls").mkdir(parents=True)
            records = {"A": submitted("A")}
            make_db(
                Path(folder) / "r.sqlite3",
                {
                    "r-ok": state_with(["x"], records),
                    "r-fb": state_with(["예산 도달", MARKER], records),
                    "r-bad": state_with(["x"], records),
                },
            )
            write_entries(out / "calls" / "SV001-1.json", [{"role": "d", "error": None}] * 3)
            write_entries(out / "calls" / "SV001-2.json", [{"role": "d", "error": None}] * 3)
            write_entries(
                out / "calls" / "SV001-3.json",
                [{"role": "d", "error": "e", "error_code": "E"}] * 2 + [{"role": "d"}],
            )
            original = [
                {
                    "행": "SV001-1",
                    "상태": "완료",
                    "코드 순위": 2,
                    "최종 순위": 2,
                    "요청 ID": "r-ok",
                },
                {
                    "행": "SV001-2",
                    "상태": "완료",
                    "코드 순위": 3,
                    "최종 순위": 1,
                    "요청 ID": "r-fb",
                },
                {
                    "행": "SV001-3",
                    "상태": "완료",
                    "코드 순위": 1,
                    "최종 순위": 1,
                    "요청 ID": "r-bad",
                },
                {"행": "SV001-4", "상태": "오류", "오류": "x"},
            ]
            (out / RESULT).write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
            before = (out / RESULT).read_bytes()
            argv = ["--reassess", "--out", str(out), "--requests", str(Path(folder) / "r.sqlite3")]
            with patch(
                "backtest.full.execute_agentic_analysis", side_effect=AssertionError("호출")
            ):
                first = main(argv)
            unchanged = (out / RESULT).read_bytes() == before
            fresh = json.loads((out / "전체실행_재집계.json").read_text(encoding="utf-8"))
            second = main(argv)
        self.assertEqual(first, 0)
        self.assertTrue(unchanged)
        self.assertEqual(
            [r["상태"] for r in fresh["rows"]], ["완료", "대체 마무리", "무효", "오류"]
        )
        self.assertEqual(
            fresh["summary"]["상태"], {"완료": 1, "대체 마무리": 1, "무효": 1, "오류": 1}
        )
        self.assertEqual(fresh["summary"]["호출 수"], 9)
        self.assertEqual(fresh["summary"]["완료 중 코드 순위 = 최종 순위"], 1)
        self.assertEqual(second, 1)


if __name__ == "__main__":
    unittest.main()
