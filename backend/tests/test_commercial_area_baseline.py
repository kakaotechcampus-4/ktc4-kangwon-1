"""음식점 밀도 백분위 계산을 검사합니다."""

import unittest
from unittest import mock

from app.agents.commercial_area import baseline
from app.agents.commercial_area.baseline import (
    SEOUL_RESTAURANT_DENSITY_PERCENTILES,
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


if __name__ == "__main__":
    unittest.main()
