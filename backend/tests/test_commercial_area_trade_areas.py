"""분석 반경과 겹치는 서울시 상권을 찾는 부분을 검사합니다."""

import math
import unittest

from app.agents.commercial_area.trade_areas import (
    DATA_PATH,
    build_trade_areas,
    load_trade_areas,
    to_epsg5181,
)

SEOUL_CITY_HALL = (37.5665, 126.9780)
BUSAN_SEOMYEON = (35.1796, 129.0756)


class ProjectionTests(unittest.TestCase):
    def test_matches_the_documented_reference_point(self):
        # floating_population/geo.py 가 pyproj 로 검증해 문서에 남긴 값.
        # 투영식이 두 벌이라 어긋나면 여기서 잡힌다.
        x, y = to_epsg5181(37.5183291, 127.1051123)
        self.assertAlmostEqual(x, 209292.3, delta=0.5)
        self.assertAlmostEqual(y, 446543.6, delta=0.5)

    def test_origin_maps_to_false_easting_and_northing(self):
        x, y = to_epsg5181(38.0, 127.0)
        self.assertAlmostEqual(x, 200000.0, delta=0.01)
        self.assertAlmostEqual(y, 500000.0, delta=0.01)

    def test_moving_east_increases_x(self):
        west, _ = to_epsg5181(37.5, 126.9)
        east, _ = to_epsg5181(37.5, 127.1)
        self.assertLess(west, east)


@unittest.skipUnless(DATA_PATH.exists(), "seoul_trade_areas.csv 가 없습니다")
class TradeAreaLookupTests(unittest.TestCase):
    def test_master_loads(self):
        areas = load_trade_areas()
        self.assertGreater(len(areas), 1000)
        self.assertTrue(all(a.code and a.area_m2 > 0 for a in areas))

    def test_every_area_has_a_known_kind(self):
        kinds = {a.kind for a in load_trade_areas()}
        self.assertTrue(kinds <= {"골목상권", "발달상권", "전통시장", "관광특구"}, kinds)

    def test_equivalent_radius_follows_from_area(self):
        area = load_trade_areas()[0]
        self.assertAlmostEqual(
            area.equivalent_radius_m, math.sqrt(area.area_m2 / math.pi), places=6
        )

    def test_seoul_centre_finds_areas_sorted_by_distance(self):
        found = build_trade_areas(*SEOUL_CITY_HALL, 500)
        self.assertTrue(found)
        distances = [t.distance_m for t in found]
        self.assertEqual(distances, sorted(distances))
        self.assertTrue(all(t.kind for t in found))

    def test_outside_seoul_returns_empty(self):
        self.assertEqual(build_trade_areas(*BUSAN_SEOMYEON, 500), [])

    def test_wider_radius_never_loses_areas(self):
        narrow = {t.code for t in build_trade_areas(*SEOUL_CITY_HALL, 200)}
        wide = {t.code for t in build_trade_areas(*SEOUL_CITY_HALL, 500)}
        self.assertTrue(narrow <= wide)

    def test_result_is_capped(self):
        # 명동처럼 상권이 빽빽한 곳에서도 목록이 무한정 길어지지 않아야 한다.
        self.assertLessEqual(len(build_trade_areas(37.5636, 126.9820, 500)), 8)

    def test_missing_file_is_treated_like_outside_seoul(self):
        self.assertEqual(load_trade_areas(DATA_PATH.with_name("없는파일.csv")), ())


if __name__ == "__main__":
    unittest.main()
