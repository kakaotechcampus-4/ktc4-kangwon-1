"""배포하는 실제 상권영역 파일로 좌표 해석을 검증합니다."""

import unittest
from dataclasses import replace
from unittest.mock import patch

from app.agents.business_lifecycle.area_resolver import (
    BusinessAreaNoDataError,
    ShapeFeature,
    _feature_to_business_area,
    resolve_area,
)
from app.agents.business_lifecycle.config import Settings
from app.schemas import Site


class BusinessAreaDataTests(unittest.TestCase):
    def test_gaerong_address_resolves_with_bundled_files(self):
        site = Site(
            input_address="서울 송파구 오금로 404",
            road_address="서울 송파구 오금로 404",
            latitude=37.4975927810188,
            longitude=127.135121781578,
        )
        with patch("socket.socket.connect", side_effect=AssertionError("외부 호출 금지")):
            area = resolve_area(site, Settings())
        self.assertEqual(area.area_code, "3120240")
        self.assertEqual(area.area_name, "개롱역")
        self.assertEqual(area.district_code, "11710")


if __name__ == "__main__":
    unittest.main()


class NearestBusinessAreaTests(unittest.TestCase):
    def choose(self, offset):
        feature = ShapeFeature(
            attributes={"TRDAR_CD": "3110001", "TRDAR_CD_NM": "대역상권"},
            bbox=(offset, -10, offset + 20, 10),
            rings=(
                ((offset, -10), (offset + 20, -10), (offset + 20, 10), (offset, 10), (offset, -10)),
            ),
        )
        site = Site(input_address="대역", road_address="대역", latitude=37.5, longitude=127.0)
        with (
            patch("app.agents.business_lifecycle.area_resolver.to_epsg5181", return_value=(0, 0)),
            patch(
                "app.agents.business_lifecycle.area_resolver.load_shape_features",
                return_value=(feature,),
            ),
            patch(
                "app.agents.business_lifecycle.area_resolver._feature_to_business_area",
                side_effect=lambda f, x, y: replace(
                    _feature_to_business_area(f, x, y), warning="기존 경고"
                ),
            ),
        ):
            return resolve_area(site, Settings())

    def test_containing_polygon_has_zero_distance(self):
        area = self.choose(-10)
        self.assertEqual(area.selection_method, "포함")
        self.assertEqual(area.selection_distance_m, 0)
        self.assertEqual(area.warning, "기존 경고")

    def test_nearest_uses_polygon_edge_not_center(self):
        area = self.choose(295)
        self.assertEqual(area.selection_method, "최근접")
        self.assertEqual(area.selection_distance_m, 295)
        self.assertIn("최근접 상권", area.warning)
        self.assertIn(self.choose(-10).warning, area.warning)

    def test_outside_three_hundred_meters_is_no_data(self):
        with self.assertRaises(BusinessAreaNoDataError):
            self.choose(301)
