"""WGS84 → EPSG:5181 투영식을 검사합니다."""

import unittest

from app.geo import to_epsg5181


class ProjectionTests(unittest.TestCase):
    def test_matches_the_documented_reference_point(self):
        # pyproj 없이 직접 구현한 투영식의 유일한 외부 기준점(app/geo.py docstring).
        # 이 값이 흔들리면 pyproj 를 쓰지 않기로 한 결정의 근거가 무너진다.
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

    def test_snyder_fourth_order_coefficient(self):
        # y 4차항이 Snyder (8-9) 의 (5 - t + 9c + 4c²) 인지 본다. 합치기 전 사본 둘은
        # (5 - 4t + ...) 였고, 그 차이가 서울에서는 1.6e-6 m 라 서울 좌표로는 잡히지 않는다.
        # 중앙자오선에서 먼 부산에서만 0.21m 로 벌어진다.
        _, y = to_epsg5181(35.1796, 129.0756)
        self.assertAlmostEqual(y, 188993.756, delta=0.01)


if __name__ == "__main__":
    unittest.main()
