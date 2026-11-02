"""성과·업종을 사용하지 않는 주소 대조와 좌표 모호성 제외를 검증합니다."""

import csv
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from backtest.cohort import address_key, build


class AddressTests(unittest.TestCase):
    def test_floor_is_ignored_but_basement_building_numbers_are_distinct(self):
        self.assertEqual(
            address_key("서울특별시 강남구 테헤란로 123 2층"),
            address_key("서울 강남구 테헤란로 123 (1층)"),
        )
        self.assertNotEqual(
            address_key("서울 강남구 테헤란로 123"),
            address_key("서울 강남구 테헤란로 지하 123"),
        )

    def test_parcel_and_mountain_are_preserved_and_incomplete_addresses_rejected(self):
        self.assertNotEqual(
            address_key("서울특별시 마포구 창전동 5-81"),
            address_key("서울특별시 마포구 창전동 산 5-81"),
        )
        self.assertIsNone(address_key("서울 강남구 테헤란로"))
        self.assertIsNone(address_key("경기도 성남시 분당구 판교로 123"))
        self.assertIsNone(address_key("서울 강남구 테헤란로 123abc"))


class CohortTests(unittest.TestCase):
    def fixtures(self, root, coordinates):
        data = root / "market.sqlite3"
        with closing(sqlite3.connect(data)) as db, db:
            db.executescript("""
                CREATE TABLE data_versions(version_id,source,quarter,file_hash);
                CREATE TABLE source_fields(version_id,columns_json);
                CREATE TABLE data_releases(release_id);
                CREATE TABLE release_versions(release_id,version_id);
                CREATE TABLE stores(row_key,latitude,longitude,payload,version_id);
            """)
            db.execute("INSERT INTO data_versions VALUES('v','stores','20262','hash')")
            db.execute("INSERT INTO data_releases VALUES(1)")
            db.execute("INSERT INTO release_versions VALUES(1,'v')")
            db.execute(
                "INSERT INTO source_fields VALUES('v',?)", (json.dumps(["도로명주소", "지번주소"]),)
            )
            for index, (latitude, longitude) in enumerate(coordinates):
                db.execute(
                    "INSERT INTO stores VALUES(?,?,?,?, 'v')",
                    (
                        str(index),
                        latitude,
                        longitude,
                        json.dumps(
                            ["서울특별시 강남구 테헤란로 123", "서울특별시 강남구 역삼동 1"]
                        ),
                    ),
                )
        source = root / "source.txt"
        with source.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["행", "주소", "실제 업종"])
            writer.writerows(
                [
                    ["a", "서울 강남구 테헤란로 123 1층", "한식 음식점"],
                    ["b", "서울 강남구 테헤란로 123 2층", "카페·비알코올 음료점"],
                    ["c", "서울 강남구 테헤란로 124", "한식 음식점"],
                ]
            )
        return source, data

    def test_same_building_coordinate_is_used_without_matching_the_target_industry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, data = self.fixtures(root, [(37.5, 127.0), (37.5, 127.0)])
            before = data.read_bytes()
            metadata = build(source, data, root / "out")
            sites = json.loads((root / "out/sites.json").read_text(encoding="utf-8"))["sites"]
            self.assertEqual(metadata["matched_n"], 2)
            self.assertEqual(metadata["exclusion_counts"], {"unmatched_address": 1})
            self.assertEqual({case["target_industry_code"] for case in sites}, {"I201", "I212"})
            self.assertEqual(sites[0]["coordinate_source"]["row_ids"], ["0", "1"])
            self.assertEqual(data.read_bytes(), before)

    def test_ambiguous_points_are_not_averaged_or_selected_using_the_label(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, data = self.fixtures(root, [(37.5, 127.0), (37.5001, 127.0)])
            with self.assertRaisesRegex(ValueError, "주소가 없습니다"):
                build(source, data, root / "out")
            self.assertFalse((root / "out").exists())


if __name__ == "__main__":
    unittest.main()
