"""반경별 집계와 집적·특화 지표 계산을 검사합니다."""

import math
import unittest

from app.agents.commercial_area.config import Settings
from app.agents.commercial_area.metrics import (
    area_km2,
    build_diversity,
    build_major_rows,
    build_middle_rows,
    build_radius_slices,
    build_restaurant_density,
    effective_categories,
    haversine_m,
    hhi,
    stores_within,
)
from app.agents.commercial_area.schemas import MiddleCode, Store

MASTER = [
    MiddleCode(code="I201", name="한식", major_code="I2", major_name="음식점업"),
    MiddleCode(code="I212", name="커피/음료", major_code="I2", major_name="음식점업"),
    MiddleCode(code="I202", name="중식", major_code="I2", major_name="음식점업"),
    MiddleCode(code="G204", name="편의점", major_code="G2", major_name="소매업"),
    MiddleCode(code="R102", name="이용/미용", major_code="R1", major_name="수리 및 개인 서비스업"),
]


def store(
    code,
    name,
    major_code,
    major_name,
    label,
    lat=37.5,
    lon=127.0,
    district_code=None,
    district_name=None,
):
    return Store(
        store_id=f"{code}-{label}",
        name=label,
        branch_name=None,
        major_code=major_code,
        major_name=major_name,
        middle_code=code,
        middle_name=name,
        small_code=None,
        small_name=None,
        latitude=lat,
        longitude=lon,
        road_address=None,
        district_code=district_code,
        district_name=district_name,
    )


def sample_stores():
    stores = [store("I201", "한식", "I2", "음식점업", f"한식{i}") for i in range(6)]
    stores += [store("I212", "커피/음료", "I2", "음식점업", f"카페{i}") for i in range(3)]
    stores.append(store("G204", "편의점", "G2", "소매업", "편의점0"))
    return stores


def ring_stores():
    near = [store("I201", "한식", "I2", "음식점업", f"가까운{i}") for i in range(4)]
    far = [store("I212", "커피/음료", "I2", "음식점업", f"먼{i}", lat=37.5027) for i in range(3)]
    return near + far


class MetricsTests(unittest.TestCase):
    def test_area_and_density(self):
        self.assertTrue(math.isclose(area_km2(500), math.pi * 0.25, rel_tol=1e-9))
        rows = build_middle_rows(sample_stores(), 500, MASTER)
        han = next(r for r in rows if r.code == "I201")
        self.assertTrue(math.isclose(han.density_per_km2, 6 / area_km2(500), rel_tol=1e-3))
        self.assertTrue(math.isclose(han.density_sq, han.density_per_km2**2, rel_tol=1e-3))

    def test_counts_sum_to_total(self):
        stores = sample_stores()
        self.assertEqual(sum(r.count for r in build_middle_rows(stores, 500, MASTER)), len(stores))
        self.assertEqual(sum(r.count for r in build_major_rows(stores, 500, MASTER)), len(stores))

    def test_master_categories_present_even_when_zero(self):
        rows = build_middle_rows(sample_stores(), 500, MASTER)
        self.assertEqual(len(rows), len(MASTER))
        zero = next(r for r in rows if r.code == "I202")
        self.assertEqual(zero.count, 0)
        self.assertIsNone(zero.lq)

    def test_same_and_diff_type_counts(self):
        stores = sample_stores()
        han = next(r for r in build_middle_rows(stores, 500, MASTER) if r.code == "I201")
        self.assertEqual(han.same_type_count, 6)
        self.assertEqual(han.diff_type_count, len(stores) - 6)

    def test_hhi_bounds_and_effective_categories(self):
        self.assertEqual(hhi([10]), 1.0)
        self.assertEqual(hhi([]), 0.0)
        self.assertTrue(0 < hhi([5, 5, 5, 5]) < 1)
        self.assertTrue(math.isclose(effective_categories(hhi([5, 5, 5, 5])), 4.0, rel_tol=1e-9))
        stores = sample_stores()
        diversity = build_diversity(
            build_major_rows(stores, 500, MASTER), build_middle_rows(stores, 500, MASTER)
        )
        self.assertTrue(0 < diversity.hhi_middle <= 1)

    def test_lq_uses_baseline_shares(self):
        rows = build_middle_rows(
            sample_stores(), 500, MASTER, {"I201": 100, "I212": 100, "G204": 200}
        )
        han = next(r for r in rows if r.code == "I201")
        self.assertTrue(math.isclose(han.lq, (6 / 10) / (100 / 400), rel_tol=1e-3))
        self.assertIsNone(next(r for r in rows if r.code == "R102").lq)

    def test_restaurant_density_counts_only_food_major(self):
        density = build_restaurant_density(sample_stores(), 500, Settings())
        self.assertTrue(math.isclose(density.value, 9 / area_km2(500), rel_tol=1e-3))
        self.assertEqual(density.unit, "stores_per_km2")
        self.assertEqual(density.store_count, 9)

    def test_unknown_category_from_api_is_added(self):
        stores = sample_stores()
        stores.append(store("Z999", "미확인업종", "Z9", "미확인", "신규"))
        rows = build_middle_rows(stores, 500, MASTER)
        self.assertEqual(len(rows), len(MASTER) + 1)


class DistrictComparisonTests(unittest.TestCase):
    def test_district_ratio_is_independent_of_local_baseline(self):
        stores = sample_stores()
        district = {"I201": 200, "I212": 200, "G204": 600}
        local = {"I201": 100, "I212": 100, "G204": 200}
        rows = build_middle_rows(stores, 500, MASTER, local, district)
        han = next(r for r in rows if r.code == "I201")

        self.assertTrue(math.isclose(han.lq, (6 / 10) / (100 / 400), rel_tol=1e-3))
        self.assertTrue(math.isclose(han.lq_district, (6 / 10) / (200 / 1000), rel_tol=1e-3))

    def test_district_ratio_is_none_without_district_counts(self):
        rows = build_middle_rows(sample_stores(), 500, MASTER, {"I201": 100})
        self.assertTrue(all(r.lq_district is None for r in rows))

    def test_district_specialization_names_the_district(self):
        from app.agents.commercial_area.metrics import build_district_specialization

        rows = build_middle_rows(sample_stores(), 500, MASTER, None, {"I201": 200, "G204": 800})
        ranks = build_district_specialization(rows, Settings(), "송파구")

        self.assertTrue(ranks)
        self.assertIn("송파구 전체", ranks[0].note)
        self.assertTrue(all(r.count >= Settings().min_count_for_specialization for r in ranks))


class RadiusSliceTests(unittest.TestCase):
    def test_haversine_matches_known_distance(self):
        self.assertTrue(math.isclose(haversine_m(37.5, 127.0, 37.5027, 127.0), 300, rel_tol=0.02))
        self.assertEqual(haversine_m(37.5, 127.0, 37.5, 127.0), 0.0)

    def test_stores_within_filters_by_distance(self):
        stores = ring_stores()
        self.assertEqual(len(stores_within(stores, 37.5, 127.0, 50)), 4)
        self.assertEqual(len(stores_within(stores, 37.5, 127.0, 500)), 7)

    def test_radius_slices_are_nested_and_ranked(self):
        settings = Settings(analysis_radius_m=500, breakdown_radii=(50, 100, 500))
        slices = build_radius_slices(ring_stores(), 37.5, 127.0, MASTER, settings)
        self.assertEqual([s.radius_m for s in slices], [50, 100, 500])
        self.assertEqual([s.store_total for s in slices], [4, 4, 7])
        self.assertEqual(slices[0].top_by_count[0].name, "한식")
        self.assertEqual(slices[-1].absent_category_count, 3)
        self.assertTrue(slices[0].explanations.store_total.startswith("반경 50m 안에"))
        self.assertNotIn("LQ", slices[0].explanations.specialization)


if __name__ == "__main__":
    unittest.main()
