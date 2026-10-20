"""분기 자료 갱신의 원자성과 이어 받기를 네트워크 없이 검증합니다."""

import asyncio
import csv
import tempfile
import unittest
from pathlib import Path

from app.local_data.database import DataValidationError, LocalDataDB
from app.local_data.refresh import collect_pages, normalize, store_rows
from scripts.build_density_baseline import CSV_FIELDS
from tests.local_data_fixture import complete_versions


class LocalDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = LocalDataDB(Path(self.temp.name) / "market.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def stage(self, quarter="20262", rows=None):
        return self.db.stage("lifecycle", quarter, rows or [self.row()], "hash" + quarter)

    @staticmethod
    def row(key="a"):
        return {
            "row_key": key,
            "area_code": "100",
            "industry_code": "CS100001",
            "payload": {"count": 1},
        }

    def test_failure_preserves_active_and_atomic_release(self):
        a = self.stage()
        first = complete_versions(self.db, [a], "20262")
        self.db.activate(first)
        b = self.stage("20263")
        with self.assertRaises(DataValidationError):
            self.db.activate([b, "missing"])
        self.assertEqual(set(self.db.active_versions()), set(first))
        b = self.stage("20263")
        second = complete_versions(self.db, [b], "20263")
        self.db.activate(second)
        self.assertEqual(set(self.db.active_versions()), set(second))

    def test_duplicate_missing_and_quarter_gap(self):
        for rows in ([self.row(), self.row()], [{"row_key": "x"}]):
            with self.assertRaises(DataValidationError):
                self.stage(rows=rows)
        a = self.stage("20262")
        versions = complete_versions(self.db, [a], "20262")
        removed = next(v for v in versions if self.db.version(v)["quarter"] == "20261")
        versions.remove(removed)
        versions.append(self.stage("20231"))
        with self.assertRaises(DataValidationError):
            self.db.activate(versions)

    def test_retention_and_row_count_drift(self):
        a = self.stage("20254")
        self.db.activate(complete_versions(self.db, [a], "20254"))
        b = self.stage("20261")
        self.db.activate(complete_versions(self.db, [b], "20261"))
        c = self.stage("20262")
        current = complete_versions(self.db, [c], "20262")
        self.db.activate(current)
        self.assertEqual(self.db.release_count(), 2)
        self.assertIsNone(self.db.version(a))
        bad = self.stage("20263", [self.row("a"), self.row("b"), self.row("c")])
        invalid = complete_versions(self.db, [bad], "20263")
        with self.assertRaises(DataValidationError):
            self.db.activate(invalid)
        self.assertEqual(set(self.db.active_versions()), set(current))

    def test_resume_pages(self):
        calls = []
        broken = True

        async def fetch(start, end):
            calls.append(start)
            if start == 1001 and broken:
                raise RuntimeError("대역 오류")
            return {
                "list_total_count": 1001,
                "row": [{"id": n} for n in range(start, min(end, 1001) + 1)],
            }

        with self.assertRaises(RuntimeError):
            asyncio.run(collect_pages(self.db, "test", fetch))
        broken = False
        rows, count = asyncio.run(collect_pages(self.db, "test", fetch))
        self.assertEqual(len(rows), 1001)
        self.assertEqual(count, 2)
        self.assertEqual(calls, [1, 1001, 1, 1001])

    def test_csv_mapping_preserves_excluded_rows_and_district_zeros(self):
        path = Path(self.temp.name) / "stores.csv"
        fields = list(CSV_FIELDS.values()) + ["시도명"]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for key, middle, small in [("a", "G215", "G21503"), ("b", "G213", "G21303")]:
                row = dict.fromkeys(fields, "")
                row.update(
                    {
                        "상가업소번호": key,
                        "상권업종대분류코드": "G2",
                        "상권업종중분류코드": middle,
                        "상권업종소분류코드": small,
                        "위도": "37.5",
                        "경도": "127.0",
                        "시군구코드": "11680",
                        "시도명": "서울특별시",
                    }
                )
                writer.writerow(row)
        version = self.db.stage("stores", "20262", store_rows(path, CSV_FIELDS), "csv")
        self.assertEqual(self.db.raw_row("stores", version, "a")["상가업소번호"], "a")
        with self.assertRaises(DataValidationError):
            self.db.validate_seoul_stores(version)
        with self.db.connection() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM stores").fetchone()[0], 2)
            self.assertEqual(
                con.execute("SELECT industry_code FROM stores WHERE row_key='a'").fetchone()[0],
                "G215B",
            )
            self.assertIsNone(
                con.execute("SELECT industry_code FROM stores WHERE row_key='b'").fetchone()[0]
            )
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM district_counts WHERE version_id=?", (version,)
                ).fetchone()[0],
                51,
            )
        path.write_text(
            path.read_text(encoding="utf-8-sig").replace("G21503", "G21599"), encoding="utf-8-sig"
        )
        with self.assertRaises(DataValidationError):
            list(store_rows(path, CSV_FIELDS))

    def test_required_raw_fields_and_numeric_values(self):
        row = {"STDR_YYQU_CD": "20262", "TRDAR_CD": "a"}
        with self.assertRaises(DataValidationError):
            normalize("lifecycle", row, "20262")
        with self.assertRaises(DataValidationError):
            normalize("floating", row, "20262")
        with self.assertRaises(DataValidationError):
            normalize("resident", row, "20262")

    def test_daily_quota_checkpoint_and_page_count_validation(self):
        self.db.reserve_http(limit=1)
        with self.assertRaises(DataValidationError):
            self.db.reserve_http(limit=1)

        async def incomplete(start, end):
            return {"list_total_count": 1001, "row": [{"id": 1}]}

        with self.assertRaises(DataValidationError):
            asyncio.run(collect_pages(self.db, "incomplete", incomplete))
        self.assertIsNone(self.db.page("incomplete", 1))

    def test_identical_import_is_idempotent(self):
        a = self.stage()
        b = self.stage()
        self.assertEqual(a, b)
        versions = complete_versions(self.db, [a], "20262")
        self.db.activate(versions)
        self.db.activate(versions)
        self.assertEqual(self.db.release_count(), 1)


if __name__ == "__main__":
    unittest.main()
