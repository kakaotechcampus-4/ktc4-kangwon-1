"""확장 업종 프로필과 업종별 밀도 집계의 대역 검증."""

import csv
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import get_args

from test_commercial_area_agent import sample_stores

from app.agents.commercial_area.trade_areas import SeoulTradeArea
from app.geo import to_epsg5181
from app.industries import DATA_DIR
from app.industries.catalog import INDUSTRIES
from app.schemas import FacilityCode
from scripts.build_density_baseline import area_km2, industry_counts, percentile_table, sample_csv


class IndustryProfilePreparationTests(unittest.TestCase):
    def test_profile_uses_catalog_and_supported_facility_codes(self):
        with (DATA_DIR / "industry_profile.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), len(INDUSTRIES))
        self.assertEqual({r["industry_code"]: r["industry_name"] for r in rows}, INDUSTRIES)
        for row in rows:
            self.assertEqual(row["reviewed"], "true")
            self.assertEqual(row["reviewed_v2"], "true")
            self.assertIn(row["day_pattern"], {"평일형", "주말형", "무관", ""})
            self.assertIn(row["target_population"], {"유동", "상주", "직장", ""})
            ages = row["target_age_bands"].split(";") if row["target_age_bands"] else []
            self.assertLessEqual(len(ages), 3)
            self.assertTrue(set(ages) <= {"10", "20", "30", "40", "50", "60"})
            facilities = row["required_facilities"].split(";") if row["required_facilities"] else []
            self.assertLessEqual(len(facilities), 3)
            self.assertTrue(set(facilities) <= set(get_args(FacilityCode)))
            self.assertEqual(bool(facilities), bool(row["max_distance_m"]))
            for field in (
                "day_pattern",
                "target_population",
                "target_age_bands",
                "required_facilities",
                "max_distance_m",
            ):
                self.assertIn(row[field + "_confidence"], {"high", "medium", "low"})
                self.assertTrue(row[field + "_rationale"])

    def test_density_counts_split_stores_and_preserves_observed_zero(self):
        seed = sample_stores()[0]
        stores = [
            replace(seed, middle_code="G215", small_code="G21503"),
            replace(seed, middle_code="G215", small_code=None),
        ]
        counts, blocked = industry_counts(stores)
        self.assertEqual(set(counts), set(INDUSTRIES))
        self.assertEqual(counts["G215B"], 1)
        self.assertEqual(counts["I201"], 0)
        self.assertEqual(blocked, {"G215", "G215B"})

    def test_seoul_csv_mapping_radius_and_percentiles(self):
        headers = [
            "상가업소번호",
            "상호명",
            "상권업종대분류코드",
            "상권업종중분류코드",
            "상권업종소분류코드",
            "위도",
            "경도",
            "시도명",
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "서울.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
                writer.writerow(["1", "화장품", "G2", "G215", "G21503", 37.5, 127.0, "서울특별시"])
                writer.writerow(
                    ["2", "멀리 있는 화장품", "G2", "G215", "G21503", 37.52, 127.0, "서울특별시"]
                )
            areas = tuple(
                SeoulTradeArea(str(i), "대역", "골목", "", "", *to_epsg5181(lat, 127.0), 1)
                for i, lat in enumerate([37.5, 37.51])
            )
            rows = sample_csv(path, "20262", areas)
        counts = [json.loads(row["counts"])["G215B"] for row in rows]
        self.assertEqual(counts, [1, 0])
        self.assertEqual(percentile_table([n / area_km2(500) for n in counts])[9], 0.64)
        self.assertTrue(all(row["reference_date"] == "20262" for row in rows))
        self.assertEqual(json.loads(rows[0]["counts"])["G215"], 0)

    def test_industry_density_baseline_reuses_interpolation(self):
        from app.agents.commercial_area.baseline import (
            SEOUL_INDUSTRY_DENSITY_PERCENTILES,
            industry_percentile,
        )

        self.assertEqual(set(SEOUL_INDUSTRY_DENSITY_PERCENTILES), set(INDUSTRIES))
        bounds = SEOUL_INDUSTRY_DENSITY_PERCENTILES["I201"]
        self.assertEqual(industry_percentile("I201", (bounds[40] + bounds[45]) / 2), 42.5)
        self.assertIsNone(industry_percentile("S202", 0))
        self.assertIsNone(industry_percentile("I201", float("nan")))
