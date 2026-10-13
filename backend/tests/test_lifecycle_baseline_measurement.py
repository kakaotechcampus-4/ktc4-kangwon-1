"""서울 전체 개폐업 기준선은 같은 전처리와 건수 합산을 사용한다."""

import unittest

from app.industries.catalog import INDUSTRY_TO_SEOUL
from scripts.measure_lifecycle_baseline import measure


class LifecycleBaselineMeasurementTests(unittest.TestCase):
    def test_merged_rates_and_missing_sources_use_existing_preprocessor(self):
        sources = INDUSTRY_TO_SEOUL["G210"]
        rows = [
            {
                "STDR_YYQU_CD": q,
                "MEGA_CD": "11",
                "SVC_INDUTY_CD": code,
                "SIMILR_INDUTY_STOR_CO": count,
                "STOR_CO": count,
                "FRC_STOR_CO": 0,
                "OPBIZ_STOR_CO": 2,
                "CLSBIZ_STOR_CO": closed,
                "OPBIZ_RT": 0,
                "CLSBIZ_RT": 0,
            }
            for q in ["20244", "20251", "20252", "20253", "20254", "20261", "20262", "20243"]
            for code, count, closed in [(sources[0], 10, 1), (sources[1], 30, 9)]
        ]
        result = measure(rows, "20262", 8)
        self.assertEqual(result["G210"]["recent_year_close_rate"], 25.0)
        self.assertEqual(result["G210"]["exposure"], 320)
        self.assertGreater(result["G210"]["zero_filled_sources"], 0)
        self.assertEqual(result["G210"]["close_rate_trend"], 0)
        self.assertNotIn("I207", result)

    def test_missing_whole_quarter_remains_incomplete(self):
        source = INDUSTRY_TO_SEOUL["I201"][0]
        rows = [
            {
                "STDR_YYQU_CD": "20262",
                "MEGA_CD": "11",
                "SVC_INDUTY_CD": source,
                "SIMILR_INDUTY_STOR_CO": 10,
                "STOR_CO": 10,
                "FRC_STOR_CO": 0,
                "OPBIZ_STOR_CO": 1,
                "CLSBIZ_STOR_CO": 1,
                "OPBIZ_RT": 0,
                "CLSBIZ_RT": 0,
            }
        ]
        result = measure(rows, "20262", 8)
        self.assertFalse(result["I201"]["data_complete"])
        self.assertIsNone(result["I201"]["turnover_rate"])
