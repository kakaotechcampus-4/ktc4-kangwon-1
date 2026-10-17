import asyncio
import csv
import json
import tempfile
import unittest
from pathlib import Path

from app.address import GeocodeError
from app.industries.catalog import INDUSTRIES
from app.schemas import Site
from backtest.run import STATE, SUMMARY, parse, run_rows

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


if __name__ == "__main__":
    unittest.main()
