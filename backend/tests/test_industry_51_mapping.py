"""서비스 51업종의 소분류 분할과 합병 비율을 검증합니다."""

import csv
import unittest
from dataclasses import replace

from test_commercial_area_metrics import sample_stores

from app.agents.business_lifecycle.preprocess import aggregate_rows
from app.agents.commercial_area.industries import map_stores
from app.agents.commercial_area.metrics import count_by_middle
from app.industries import DATA_DIR, lookup


class Industry51MappingTests(unittest.TestCase):
    def test_split_catalog_is_generated_from_csv_and_missing_small_is_not_inferred(self):
        from app.industries.catalog import EXCLUDED_SMALLS, MIDDLE_TO_INDUSTRY, SPLIT_MIDDLES

        with (DATA_DIR / "small_to_industry.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(SPLIT_MIDDLES, {r["source_middle_code"] for r in rows})
        self.assertEqual(EXCLUDED_SMALLS, {r["small_code"] for r in rows if not r["industry_code"]})
        self.assertFalse(SPLIT_MIDDLES.intersection(MIDDLE_TO_INDUSTRY))
        self.assertIsNone(lookup.service_code("G213", None))
        self.assertEqual(lookup.service_code("G215B", None), "G215B")

    def test_cosmetics_and_sports_use_small_codes_and_unknown_split_is_excluded(self):
        base = sample_stores()[0]
        stores = [
            replace(base, store_id="cosmetics", middle_code="G215", small_code="G21503"),
            replace(base, store_id="medical", middle_code="G215", small_code="G21502"),
            replace(base, store_id="sports", middle_code="G213", small_code="G21304"),
            replace(base, store_id="unknown", middle_code="G215", small_code=None),
            replace(base, store_id="music", middle_code="G213", small_code="G21303"),
        ]
        mapped = map_stores(stores)
        self.assertEqual(dict(count_by_middle(mapped)), {"G215B": 1, "G215": 1, "G203": 1})
        self.assertIsNone(lookup.service_code("G215", None))
        self.assertEqual(lookup.service_code("G212", None), "G210")

    def test_merged_education_rates_are_recomputed_from_summed_counts(self):
        rows = [
            {
                "stdr_yyqu_cd": "20262",
                "trdar_cd": "area",
                "svc_induty_cd": source,
                "similr_induty_stor_co": stores,
                "stor_co": stores,
                "frc_stor_co": 0,
                "opbiz_stor_co": 0,
                "clsbiz_stor_co": closed,
                "opbiz_rt": 0,
                "clsbiz_rt": 50,
            }
            for source, stores, closed in (
                ("CS200001", 10, 5),
                ("CS200002", 90, 0),
                ("CS200003", 90, 0),
                ("CS200004", 90, 0),
                ("CS200005", 90, 0),
            )
        ]
        frame = aggregate_rows(rows, "area", "20262", 1).set_index("service_id")
        self.assertEqual(frame.loc["P105", "latest_store_count"], 370)
        self.assertEqual(frame.loc["P105", "recent_year_close_rate"], 1.35)
        self.assertFalse(frame.loc["M107", "data_available"])
