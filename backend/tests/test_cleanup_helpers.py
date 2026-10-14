"""공개 계산 이름과 공통 거리·분기 이동이 기존 규칙을 유지하는지 확인합니다."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.agents.business_lifecycle.client import get_recent_quarters
from app.agents.business_lifecycle.preprocess import aggregate_rows
from app.agents.commercial_area.client import check_header, extract_items
from app.agents.commercial_area.metrics import haversine_m as old_distance
from app.agents.floating_population.geo import overlapping_areas
from app.agents.floating_population.metrics import aggregate, daily_benchmark, trend
from app.agents.floating_population.population import age_share
from app.geo import haversine_m
from app.db.connection import readonly
from app.seoul import previous_quarter, shift_quarter


class SharedHelperTests(unittest.TestCase):
    def test_readonly_connection_cannot_write_or_create_missing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE sample(value INTEGER)")
                db.execute("INSERT INTO sample VALUES(1)")
            with readonly(path) as db:
                self.assertEqual(db.execute("SELECT value FROM sample").fetchone()["value"], 1)
                with self.assertRaises(sqlite3.OperationalError):
                    db.execute("INSERT INTO sample VALUES(2)")
            with self.assertRaises(sqlite3.ProgrammingError):
                db.execute("SELECT 1")
            missing = Path(directory) / "missing.sqlite3"
            with self.assertRaises(sqlite3.OperationalError):
                with readonly(missing):
                    pass
            self.assertFalse(missing.exists())

    def test_public_calculation_exports(self):
        for function in (
            aggregate_rows,
            check_header,
            extract_items,
            overlapping_areas,
            aggregate,
            daily_benchmark,
            trend,
            age_share,
        ):
            self.assertTrue(callable(function))
            self.assertFalse(function.__name__.startswith("_"))

    def test_distance_reexport_is_the_same_function(self):
        self.assertIs(old_distance, haversine_m)
        self.assertEqual(haversine_m(37.5, 127.0, 37.5, 127.0), 0.0)
        self.assertAlmostEqual(haversine_m(37.5, 127.0, 37.5027, 127.0), 300.22630194037)

    def test_quarter_boundaries_and_recent_window(self):
        for year in (2023, 2024, 2025):
            for quarter in range(1, 5):
                code = f"{year}{quarter}"
                expected = f"{year - 1}4" if quarter == 1 else f"{year}{quarter - 1}"
                self.assertEqual(previous_quarter(code), expected)
                self.assertEqual(shift_quarter(code, -1), expected)
                self.assertEqual(shift_quarter(code, -4), f"{year - 1}{quarter}")
                self.assertEqual(shift_quarter(shift_quarter(code, -5), 5), code)
        self.assertEqual(
            get_recent_quarters("20262", 5), ["20252", "20253", "20254", "20261", "20262"]
        )
        for code in ("20260", "20265", "2026", "xxxxx"):
            with self.assertRaises(ValueError):
                shift_quarter(code, -1)


if __name__ == "__main__":
    unittest.main()
