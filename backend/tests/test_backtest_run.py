import asyncio
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.address import GeocodeError
from app.industries.catalog import INDUSTRIES
from app.schemas import Site
from backtest.run import STATE, SUMMARY, check_resume_inputs, file_sha256, main, parse, run_rows

CODES = list(INDUSTRIES)[:3]


def row(number, code=CODES[0], address="서울 마포구 와우산로 94"):
    return {
        "업종코드": "SV001",
        "업종": INDUSTRIES[code],
        "그룹": "1",
        "순번": str(number),
        "상호": "가",
        "주소": address,
    }


def report_rows():
    items = {
        name: {"status": "unknown", "grade": None, "points": None, "value": None, "reason": ""}
        for name in ("D1", "D2", "D3", "D4", "C1", "C4", "S1", "S2", "S3", "S4", "L")
    }
    return [
        {
            "code": code,
            "name": INDUSTRIES[code],
            "items": items,
            "lower": 60 - i * 10,
            "upper": 90,
            "coverage": 0.8,
            "regulation": "해당 없음",
            "badge": "보류",
        }
        for i, code in enumerate(CODES)
    ]


class FakeScore:
    def __init__(self, failures=None, outside=False):
        self.calls = []
        self.failures = failures or {}
        self.outside = outside

    async def __call__(self, address, *, local_data_path, db_path, request_id):
        self.calls.append(request_id)
        number = len(self.calls)
        if number in self.failures:
            raise self.failures[number]
        site = Site(input_address=address, road_address=address, latitude=37.5, longitude=127.0)
        method = "미선택" if self.outside else "포함"
        data = {
            "commercial_area": {"by_middle": [{"code": CODES[1], "count": 7}]},
            "area_selection": {"method": method},
        }
        return site, data, {"rows": report_rows()}


def run(rows, out, score, state=None, limit=None):
    return asyncio.run(
        run_rows(
            rows,
            out=out,
            data_path=Path("x"),
            requests_db=Path("y"),
            score=score,
            state=state,
            limit=limit,
        )
    )


def read_summary(out):
    with (out / SUMMARY).open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


class RunRowsTests(unittest.TestCase):
    def test_writes_summary_scores_and_state(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            result = run([row(1), row(2, code=CODES[2])], out, FakeScore())
            summary = read_summary(out)
            state = json.loads((out / STATE).read_text(encoding="utf-8"))
        self.assertIsNone(result["stopped"])
        self.assertEqual([s["순위"] for s in summary], ["1", "3"])
        self.assertEqual(summary[0]["점포 수 순위"], "2")
        self.assertEqual(len(state["scores"]), 6)

    def test_bad_address_is_its_own_status(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            run([row(1)], out, FakeScore({1: GeocodeError("NOT_FOUND", "없음")}))
            self.assertEqual(read_summary(out)[0]["상태"], "주소 변환 실패")

    def test_outside_area_is_marked(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            run([row(1)], out, FakeScore(outside=True))
            self.assertEqual(read_summary(out)[0]["상태"], "상권 밖")

    def test_same_error_three_times_stops(self):
        error = RuntimeError("같은 오류")
        score = FakeScore({1: error, 2: error, 3: error})
        with tempfile.TemporaryDirectory() as folder:
            result = run([row(n) for n in range(1, 6)], Path(folder), score)
        self.assertEqual(result["stopped"], "repeated_error")
        self.assertEqual(len(score.calls), 3)

    def test_resume_skips_done_rows_and_retries_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            run([row(1), row(2)], out, FakeScore({2: RuntimeError("일시 오류")}))
            state = json.loads((out / STATE).read_text(encoding="utf-8"))
            again = FakeScore()
            run([row(1), row(2)], out, again, state=state)
            summary = read_summary(out)
        self.assertEqual(len(again.calls), 1)
        self.assertEqual([s["행"] for s in summary], ["SV001-1", "SV001-2"])
        self.assertEqual([s["상태"] for s in summary], ["완료", "완료"])

    def test_limit_counts_only_new_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            run([row(n) for n in range(1, 5)], out, FakeScore(), limit=2)
            state = json.loads((out / STATE).read_text(encoding="utf-8"))
            again = FakeScore()
            run([row(n) for n in range(1, 5)], out, again, state=state, limit=1)
            self.assertEqual(len(again.calls), 1)
            self.assertEqual(len(read_summary(out)), 3)


class ParseTests(unittest.TestCase):
    def base(self, out):
        return [
            "--input",
            "a.csv",
            "--data",
            "d.sqlite3",
            "--baselines",
            "b.json",
            "--out",
            str(out),
        ]

    def test_existing_out_needs_resume(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(SystemExit):
            parse(self.base(Path(folder)))

    def test_resume_needs_state(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(SystemExit):
            parse([*self.base(Path(folder)), "--resume"])

    def test_new_out_is_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            args = parse(self.base(Path(folder) / "new"))
        self.assertFalse(args.resume)


VERSIONS = [{"version_id": "v1", "file_hash": "aa"}, {"version_id": "v2", "file_hash": "bb"}]
FULL_VERSIONS = [{**v, "source": "stores", "quarter": "20234", "row_count": 1} for v in VERSIONS]


def prepare_resume(folder, *, kept_copy=True, same_baseline=True, same_data=True):
    root = Path(folder)
    out = root / "out"
    out.mkdir()
    baseline = root / "baselines.json"
    baseline.write_text(
        json.dumps({"quarter": "20234", "lifecycle": {}, "floating": {}, "density": {}}),
        encoding="utf-8",
    )
    kept = baseline.read_text(encoding="utf-8") if same_baseline else '{"x": 1}'
    if kept_copy:
        (out / "baseline.json").write_text(kept, encoding="utf-8")
    sha = file_sha256(out / "baseline.json") if kept_copy else file_sha256(baseline)
    if not kept_copy and not same_baseline:
        sha = "0" * 64
    versions = FULL_VERSIONS if same_data else FULL_VERSIONS[:1]
    (out / "run_meta.json").write_text(
        json.dumps({"runs": [{"baselines": {"sha256": sha}, "data": {"versions": versions}}]}),
        encoding="utf-8",
    )
    return out, baseline, {"versions": FULL_VERSIONS}


class ResumeInputTests(unittest.TestCase):
    def check(self, **kwargs):
        with tempfile.TemporaryDirectory() as folder:
            out, baseline, data = prepare_resume(folder, **kwargs)
            return check_resume_inputs(out, baseline, data)

    def test_same_inputs_pass(self):
        self.assertIsNone(self.check())

    def test_changed_baseline_is_refused(self):
        self.assertIn("기준선", self.check(same_baseline=False))

    def test_changed_baseline_is_refused_without_a_kept_copy(self):
        self.assertIn("기준선", self.check(kept_copy=False, same_baseline=False))

    def test_same_baseline_without_a_kept_copy_passes(self):
        self.assertIsNone(self.check(kept_copy=False))

    def test_changed_data_is_refused(self):
        self.assertIn("자료", self.check(same_data=False))

    def test_main_refuses_before_scoring(self):
        with tempfile.TemporaryDirectory() as folder:
            out, baseline, data = prepare_resume(folder, same_baseline=False)
            (out / STATE).write_text("{}", encoding="utf-8")
            sample = Path(folder) / "a.csv"
            sample.write_text(
                f"업종코드,업종,그룹,순번,상호,주소\nSV001,{INDUSTRIES[CODES[0]]},1,1,가,서울\n",
                encoding="utf-8-sig",
            )
            argv = [
                "--input",
                str(sample),
                "--data",
                "d",
                "--baselines",
                str(baseline),
                "--out",
                str(out),
                "--resume",
            ]
            with (
                patch("backtest.run.load_environment"),
                patch("backtest.run.check_history_db", return_value=data),
                patch("backtest.run.asyncio.run", side_effect=AssertionError("채점 시작")),
            ):
                self.assertEqual(main(argv), 1)


if __name__ == "__main__":
    unittest.main()
