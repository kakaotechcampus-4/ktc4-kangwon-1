"""상권 응답 존재와 업종 원천 행 누락을 구분합니다."""

import unittest

import pandas as pd

from app.agents.business_lifecycle.preprocess import aggregate_rows


def source_row(quarter, source, stores=20, opened=2, closed=1):
    return {
        "stdr_yyqu_cd": quarter,
        "trdar_cd": "area",
        "svc_induty_cd": source,
        "similr_induty_stor_co": stores,
        "stor_co": stores,
        "frc_stor_co": 0,
        "opbiz_stor_co": opened,
        "clsbiz_stor_co": closed,
        "opbiz_rt": 0,
        "clsbiz_rt": 0,
    }


class ZeroFillTests(unittest.TestCase):
    def test_partial_sources_in_present_quarter_are_zero_filled_and_marked(self):
        frame = aggregate_rows([source_row("20244", "CS100008")], "area", "20244", 1)
        row = frame.set_index("service_id").loc["I210"]
        self.assertEqual(row["latest_store_count"], 20)
        self.assertEqual(row["period_open_count"], 2)
        self.assertEqual(row["period_close_count"], 1)
        self.assertEqual(row["data_status"], "observed")
        self.assertTrue(row["data_complete"])
        self.assertEqual(row["zero_filled_sources"], 3)
        detail = next(
            r for r in frame.attrs["quarterly_detail"]["industries"] if r["industry_id"] == "I210"
        )
        self.assertEqual(detail["zero_filled_sources"], 3)

    def test_absent_area_quarter_remains_missing(self):
        frame = aggregate_rows([source_row("20244", "CS100008")], "area", "20244", 2)
        row = frame.set_index("service_id").loc["I210"]
        self.assertEqual(row["data_status"], "incomplete")
        self.assertTrue(pd.isna(row["period_open_count"]))
        self.assertEqual(row["zero_filled_sources"], 3)
        detail = next(
            r for r in frame.attrs["quarterly_detail"]["industries"] if r["industry_id"] == "I210"
        )
        self.assertEqual(detail["store_counts"], [None, 20])

    def test_all_sources_absent_keeps_missing_status_and_undefined_rate(self):
        frame = aggregate_rows([source_row("20244", "CS100001")], "area", "20244", 1)
        row = frame.set_index("service_id").loc["I210"]
        self.assertEqual(row["latest_store_count"], 0)
        self.assertTrue(pd.isna(row["recent_year_close_rate"]))
        self.assertFalse(row["data_available"])
        self.assertFalse(row["data_complete"])
        self.assertEqual(row["data_status"], "missing")
        self.assertEqual(row["zero_filled_sources"], 4)
