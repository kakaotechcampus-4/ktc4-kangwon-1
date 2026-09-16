"""공통 업종 어휘 표가 스스로 모순되지 않는지 검사합니다."""

import unittest

from app.agents.commercial_area.config import Settings
from app.agents.commercial_area.upjong import load_middle_master
from app.industries.catalog import (
    EXCLUDED_SEOUL_INDUSTRIES,
    EXPECTED_INDUSTRY_COUNT,
    INDUSTRIES,
    INDUSTRIES_WITHOUT_SEOUL,
    INDUSTRY_MAJORS,
    INDUSTRY_TO_LEGACY70,
    INDUSTRY_TO_SEOUL,
    LEGACY70_TO_INDUSTRY,
    SEOUL_TO_INDUSTRY,
)
from app.industries.lookup import normalize_name

LEGACY_IDS = range(1, 71)


class CatalogTests(unittest.TestCase):
    def test_industry_count_matches_declaration(self):
        self.assertEqual(len(INDUSTRIES), EXPECTED_INDUSTRY_COUNT)
        self.assertEqual(len(INDUSTRY_MAJORS), EXPECTED_INDUSTRY_COUNT)

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
        # 개폐업이 "서울시 자료로는 못 만든다"고 한 업종의 대상들. 우리 자료가 메우는 자리다.
        # G212(생활용품)만 예외 — 서울시 악기·조명용품이 붙어 있어 단독이 아니다.
        for code in (
            "I206",
            "Q101",
            "Q104",
            "S208",
            "S210",
            "S211",
            "M105",
            "M106",
            "M107",
            "M109",
        ):
            self.assertIn(code, INDUSTRIES_WITHOUT_SEOUL)
        self.assertNotIn("G212", INDUSTRIES_WITHOUT_SEOUL)


class Legacy70Tests(unittest.TestCase):
    def test_every_legacy_industry_is_covered(self):
        self.assertEqual(set(LEGACY70_TO_INDUSTRY), set(LEGACY_IDS))

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
