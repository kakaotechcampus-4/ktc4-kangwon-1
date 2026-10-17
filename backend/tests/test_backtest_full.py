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
from backtest.full import RESULT, compare, main, run_full, snapshot_rows

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
            results = asyncio.run(
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
            results = asyncio.run(
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
            ]
            with (
                patch("backtest.full.load_environment"),
                patch.dict(os.environ, {"ELICE_API_KEY": ""}),
            ):
                self.assertEqual(main(argv), 1)


if __name__ == "__main__":
    unittest.main()
