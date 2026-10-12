"""SHP의 외곽/구멍 방향을 사용하는 순면적과 선택을 확인합니다."""

import unittest
from itertools import permutations

from app.agents.business_lifecycle.area_resolver import (
    ShapeFeature,
    _feature_area,
    polygon_contains_point,
)


def square(x1, y1, x2, y2, *, hole=False):
    ring = ((x1, y1), (x1, y2), (x2, y2), (x2, y1), (x1, y1))
    return tuple(reversed(ring)) if hole else ring


def feature(*rings):
    return ShapeFeature({}, (0, 0, 40, 40), tuple(rings))


class GeometryHolesTests(unittest.TestCase):
    def test_outer_ring_area(self):
        self.assertEqual(_feature_area(feature(square(0, 0, 10, 10))), 100)

    def test_hole_area_is_subtracted(self):
        self.assertEqual(
            _feature_area(feature(square(0, 0, 10, 10), square(2, 2, 8, 8, hole=True))), 64
        )

    def test_separate_outer_polygons_are_added(self):
        self.assertEqual(_feature_area(feature(square(0, 0, 10, 10), square(20, 20, 22, 22))), 104)

    def test_nested_island_and_ring_order(self):
        rings = (square(0, 0, 10, 10), square(1, 1, 9, 9, hole=True), square(2, 2, 4, 4))
        for ordered in permutations(rings):
            self.assertEqual(_feature_area(feature(*ordered)), 40)
        self.assertFalse(polygon_contains_point(rings, 5, 5))
        self.assertTrue(polygon_contains_point(rings, 3, 3))

    def test_overlap_selection_uses_net_area(self):
        holed = feature(square(0, 0, 10, 10), square(2, 2, 8, 8, hole=True))
        solid = feature(square(0, 0, 9, 9))
        candidates = [f for f in (holed, solid) if polygon_contains_point(f.rings, 1, 1)]
        self.assertIs(min(candidates, key=_feature_area), holed)
