"""음식점 밀도 백분위 계산을 검사합니다."""

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.agents.commercial_area import baseline
from app.agents.commercial_area.baseline import (
    SEOUL_RESTAURANT_DENSITY_PERCENTILES,
    load_density_percentiles,
    seoul_percentile,
)

# 5%p 간격 19개. 실제 경계표와 같은 모양의 가짜 분포.
FAKE = tuple(float(v) for v in range(100, 2000, 100))


class PercentileTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(baseline, "SEOUL_RESTAURANT_DENSITY_PERCENTILES", FAKE)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_below_the_distribution_is_zero(self):
        self.assertEqual(seoul_percentile(0.0), 0.0)
        self.assertEqual(seoul_percentile(50.0), 0.0)

    def test_above_the_distribution_is_hundred(self):
        self.assertEqual(seoul_percentile(FAKE[-1]), 100.0)
        self.assertEqual(seoul_percentile(99_999.0), 100.0)

    def test_boundary_values_land_on_their_step(self):
        self.assertEqual(seoul_percentile(FAKE[0]), 5.0)
        self.assertEqual(seoul_percentile(FAKE[1]), 10.0)

    def test_midpoint_is_interpolated(self):
        middle = (FAKE[0] + FAKE[1]) / 2
        self.assertAlmostEqual(seoul_percentile(middle), 7.5, places=1)

    def test_result_rises_with_density(self):
        values = [seoul_percentile(v) for v in (150.0, 500.0, 1200.0, 1850.0)]
        self.assertEqual(values, sorted(values))
        self.assertTrue(all(0.0 <= v <= 100.0 for v in values))

    def test_negative_density_has_no_answer(self):
        self.assertIsNone(seoul_percentile(-1.0))


class EmptyTableTests(unittest.TestCase):
    def test_without_a_table_there_is_no_percentile(self):
        with mock.patch.object(baseline, "SEOUL_RESTAURANT_DENSITY_PERCENTILES", ()):
            self.assertIsNone(seoul_percentile(300.0))


class ShippedTableTests(unittest.TestCase):
    def test_table_is_sorted_and_sized_for_five_point_steps(self):
        table = SEOUL_RESTAURANT_DENSITY_PERCENTILES
        if not table:
            self.skipTest("경계표가 아직 없습니다")
        self.assertEqual(len(table), 19)
        self.assertEqual(list(table), sorted(table))
        self.assertGreater(table[0], 0)

    def test_industry_csv_preserves_all_original_values(self):
        table = baseline.SEOUL_INDUSTRY_DENSITY_PERCENTILES
        digest = hashlib.sha256(
            json.dumps(table, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(len(table), 51)
        self.assertEqual(digest, "ae1406fd5ced28ad9318b9c4ee16460d0f766c5768ef2b31fd5495441feae24e")
        for bounds in table.values():
            self.assertEqual(list(bounds), list(range(5, 100, 5)))

    def test_invalid_csv_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "density.csv"
            header = ["industry_code", *(f"p{p}" for p in range(5, 100, 5))]
            for values in ([1.0] * 19, [float("nan")] * 19, [2.0, *([1.0] * 18)]):
                with self.subTest(values=values), path.open("w", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(header)
                    writer.writerow(["G202", *values])
                with self.assertRaises(ValueError):
                    load_density_percentiles(path)

    def test_complete_sample_emits_loader_compatible_csv(self):
        from scripts import build_density_baseline as build

        samples = {
            str(index): {
                "reference_date": "20262",
                "blocked_codes": "[]",
                "counts": json.dumps({code: index for code in build.INDUSTRIES}),
            }
            for index in range(2)
        }
        areas = [mock.Mock(code=code) for code in samples]
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(build, "load_industry_done", return_value=samples),
            mock.patch.object(build, "load_trade_areas", return_value=areas),
        ):
            path = Path(directory) / "density.csv"
            self.assertEqual(build.emit_industries(path), 0)
            table = load_density_percentiles(path)
            self.assertEqual(table["G202"][50], 0.64)
            self.assertEqual(len(table), 51)
            samples.pop("1")
            before = path.read_bytes()
            self.assertEqual(build.emit_industries(path), 1)
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
