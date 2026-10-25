"""지도 도구의 업종·시설 선택과 반경·표본 경계를 검증합니다."""

import unittest

from pydantic import ValidationError

from app.agentic.contracts import MapSearchInput


class MapContractTests(unittest.TestCase):
    def test_query_requires_exactly_one_target(self):
        self.assertEqual(MapSearchInput(industry_code="I212", radius_m=500).industry_code, "I212")
        self.assertEqual(MapSearchInput(facility_code="SC4", radius_m=50).facility_code, "SC4")
        for update in (
            {},
            {"industry_code": "bad"},
            {"facility_code": "bad"},
            {"industry_code": "I212", "facility_code": "SC4"},
        ):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                MapSearchInput.model_validate({"radius_m": 500, **update})

    def test_radius_and_sample_count_boundaries(self):
        for update in ({"radius_m": 49}, {"radius_m": 501}, {"limit": 0}, {"limit": 21}):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                MapSearchInput.model_validate({"industry_code": "I212", "radius_m": 500, **update})
