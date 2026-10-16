"""기준선 측정과 시간대 백분위의 대역 검증."""

import unittest
from unittest.mock import patch

from app.agents.floating_population import baseline
from app.agents.floating_population.models import AGE_BANDS, DAYS, TIME_BANDS, FlpopRecord
from scripts.measure_flpop_baseline import measure


class BaselineMeasurementTests(unittest.TestCase):
    def test_time_band_percentile_boundaries_and_interpolation(self):
        with patch.object(
            baseline, "TIME_BAND_DAILY_PERCENTILES", {"11_14": {5: 10, 50: 100, 95: 190}}
        ):
            for value, expected in ((0, 5), (10, 5), (55, 28), (100, 50), (190, 95), (200, 99)):
                with self.subTest(value=value):
                    self.assertEqual(baseline.time_band_percentile("11_14", value), expected)
            with self.assertRaises(KeyError):
                baseline.time_band_percentile("invalid", 100)
            for value in (-1, float("nan"), float("inf")):
                with self.subTest(invalid=value), self.assertRaises(ValueError):
                    baseline.time_band_percentile("11_14", value)

    def test_daily_total_percentile_boundaries_and_interpolation(self):
        with patch.object(baseline, "DAILY_TOTAL_PERCENTILES", {5: 10, 50: 100, 95: 190}):
            for value, expected in ((0, 5), (10, 5), (55, 28), (100, 50), (190, 95), (200, 99)):
                with self.subTest(value=value):
                    self.assertEqual(baseline.daily_total_percentile(value), expected)
            for value in (-1, float("nan"), float("inf")):
                with self.subTest(invalid=value), self.assertRaises(ValueError):
                    baseline.daily_total_percentile(value)

    def test_pattern_percentile_reuses_boundaries(self):
        with patch.object(
            baseline, "PATTERN_DAILY_PERCENTILES", {"식사형": {5: 10, 50: 100, 95: 190}}
        ):
            self.assertEqual(baseline.pattern_percentile("식사형", 55), 28)
            with self.assertRaises(KeyError):
                baseline.pattern_percentile("없는패턴", 55)
            with self.assertRaises(ValueError):
                baseline.pattern_percentile("식사형", -1)

    def test_measure_uses_weighted_shares_and_daily_band_counts(self):
        records = [
            FlpopRecord(
                trdar_cd=str(i),
                stdr_yyqu_cd="20262",
                total=total,
                male=total / 2,
                female=total / 2,
                by_age={a: total if a == ("10" if i == 0 else "20") else 0 for a in AGE_BANDS},
                by_time={b: total if b == "11_14" else 0 for b in TIME_BANDS},
                by_day={d: total / 7 for d in DAYS},
            )
            for i, total in enumerate((91, 273))
        ]
        result = measure(records, "20262", {"식사형": ("11_14", "17_21")})
        self.assertEqual(result["AGE_SHARE_AVG"]["20"], 0.75)
        self.assertEqual(result["AGE_SHARE_AVG"]["10"], 0.25)
        self.assertEqual(result["TIME_PER_HOUR_SHARE_AVG"]["11_14"], 1)
        self.assertEqual(result["WEEKEND_TO_WEEKDAY_AVG"], 1)
        self.assertEqual(result["SCALE_PERCENTILES"][50], 182)
        self.assertEqual(result["DAILY_TOTAL_PERCENTILES"][50], 2)
        self.assertEqual(result["PATTERN_DAILY_PERCENTILES"]["식사형"][50], 2)
        self.assertEqual(result["PATTERN_TIME_PER_HOUR_SHARE_AVG"]["식사형"], 1)
        self.assertEqual(result["TIME_BAND_DAILY_PERCENTILES"]["11_14"][50], 2)
        with self.assertRaises(ValueError):
            measure(records + records[:1], "20262")
