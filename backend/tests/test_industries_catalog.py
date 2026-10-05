"""공통 업종 어휘 표가 스스로 모순되지 않는지 검사합니다."""

import unittest

from app.agents.commercial_area.config import Settings
from app.agents.commercial_area.industries import load_middle_master
from app.industries.catalog import (
    EXCLUDED_SEOUL_INDUSTRIES,
    EXPECTED_INDUSTRY_COUNT,
    INDUSTRIES,
    INDUSTRIES_WITHOUT_SEOUL,
    INDUSTRY_MAJORS,
    INDUSTRY_TO_LEGACY70,
    INDUSTRY_TO_SEOUL,
    LEGACY70_TO_INDUSTRY,
    PUBLIC_MIDDLE_TO_INDUSTRY,
    PUBLIC_SMALL_TO_INDUSTRY,
    SEOUL_TO_INDUSTRY,
)
from app.industries.lookup import normalize_name

LEGACY_IDS = range(1, 71)


class CatalogTests(unittest.TestCase):
    def test_industry_count_matches_declaration(self):
        self.assertEqual(EXPECTED_INDUSTRY_COUNT, 51)
        self.assertEqual(len(INDUSTRIES), EXPECTED_INDUSTRY_COUNT)
        self.assertEqual(len(INDUSTRY_MAJORS), EXPECTED_INDUSTRY_COUNT)

    def test_codes_and_names_are_unique(self):
        self.assertEqual(len(INDUSTRIES), len(set(INDUSTRIES)))
        self.assertEqual(len(INDUSTRIES), len(set(INDUSTRIES.values())))

    def test_names_stay_distinct_after_normalization(self):
        keys = [normalize_name(name) for name in INDUSTRIES.values()]
        self.assertEqual(len(keys), len(set(keys)))

    def test_major_code_maps_to_one_name(self):
        majors = {}
        for code, name in INDUSTRY_MAJORS.values():
            self.assertEqual(majors.setdefault(code, name), name)


class SeoulLinkTests(unittest.TestCase):
    def test_every_link_points_at_a_known_industry(self):
        for code in SEOUL_TO_INDUSTRY.values():
            self.assertIn(code, INDUSTRIES)

    def test_excluded_industry_has_no_link(self):
        for code in EXCLUDED_SEOUL_INDUSTRIES:
            self.assertNotIn(code, SEOUL_TO_INDUSTRY)

    def test_forward_and_reverse_agree(self):
        rebuilt = {}
        for seoul_code, code in SEOUL_TO_INDUSTRY.items():
            rebuilt.setdefault(code, []).append(seoul_code)
        self.assertEqual(
            {k: tuple(sorted(v)) for k, v in rebuilt.items()},
            {k: tuple(sorted(v)) for k, v in INDUSTRY_TO_SEOUL.items()},
        )

    def test_industries_without_seoul_are_exactly_the_unlinked_ones(self):
        linked = set(SEOUL_TO_INDUSTRY.values())
        self.assertEqual(set(INDUSTRIES_WITHOUT_SEOUL), set(INDUSTRIES) - linked)

    def test_unlinked_industries_are_the_ones_seoul_cannot_supply(self):
        self.assertEqual(
            set(INDUSTRIES_WITHOUT_SEOUL),
            {"SV046", "SV047", "SV048", "SV049", "SV050", "SV051"},
        )


class PublicLinkTests(unittest.TestCase):
    def test_every_link_points_at_a_known_industry(self):
        for code in (*PUBLIC_MIDDLE_TO_INDUSTRY.values(), *PUBLIC_SMALL_TO_INDUSTRY.values()):
            self.assertIn(code, INDUSTRIES)

    def test_split_middle_categories_use_only_small_codes(self):
        self.assertNotIn("G213", PUBLIC_MIDDLE_TO_INDUSTRY)
        self.assertNotIn("G215", PUBLIC_MIDDLE_TO_INDUSTRY)
        self.assertEqual(PUBLIC_SMALL_TO_INDUSTRY["G21304"], "SV002")
        self.assertEqual(PUBLIC_SMALL_TO_INDUSTRY["G21305"], "SV002")
        self.assertEqual(PUBLIC_SMALL_TO_INDUSTRY["G21301"], "SV009")
        self.assertEqual(PUBLIC_SMALL_TO_INDUSTRY["G21501"], "SV010")
        self.assertEqual(PUBLIC_SMALL_TO_INDUSTRY["G21503"], "SV011")


class Legacy70Tests(unittest.TestCase):
    def test_unmapped_legacy_sources_are_not_guessed(self):
        self.assertEqual(set(LEGACY_IDS) - set(LEGACY70_TO_INDUSTRY), {14, 34, 43, 59, 67})

    def test_every_link_points_at_a_known_industry(self):
        for codes in LEGACY70_TO_INDUSTRY.values():
            self.assertTrue(codes)
            for code in codes:
                self.assertIn(code, INDUSTRIES)

    def test_forward_and_reverse_agree(self):
        rebuilt = {}
        for legacy_id, codes in LEGACY70_TO_INDUSTRY.items():
            for code in codes:
                rebuilt.setdefault(code, []).append(legacy_id)
        self.assertEqual(
            {k: tuple(sorted(v)) for k, v in rebuilt.items()},
            {k: tuple(sorted(v)) for k, v in INDUSTRY_TO_LEGACY70.items()},
        )

    def test_split_industries_are_reported_as_tuples(self):
        # 개폐업 하나가 중분류 여럿으로 갈라진다. 점수를 그대로 복제하면 안 되는 자리다.
        self.assertGreater(len(LEGACY70_TO_INDUSTRY[33]), 1)


class SourceOfTruthTests(unittest.TestCase):
    def test_every_code_exists_in_the_sbiz_master(self):
        master = {row.code for row in load_middle_master(Settings())}
        self.assertTrue(master)
        self.assertEqual(set(INDUSTRIES), master)


if __name__ == "__main__":
    unittest.main()
