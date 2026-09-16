"""서로 다른 표기와 다른 원천의 코드가 같은 업종으로 모이는지 검사합니다."""

import unittest

from app.industries import lookup
from app.schemas import Category


class NameNormalizationTests(unittest.TestCase):
    def test_team_vocabularies_resolve_to_one_industry(self):
        # 지금 팀 안에서 갈려 있는 세 표기. 이게 합쳐지는 게 이 모듈의 존재 이유다.
        found = [
            lookup.find_by_name(name) for name in ("한식음식점", "한식 음식점업", "한식음식점업")
        ]
        self.assertTrue(all(found))
        self.assertEqual({industry.code for industry in found}, {"I201"})

    def test_unknown_name_returns_none(self):
        self.assertIsNone(lookup.find_by_name("존재하지 않는 업종"))
        self.assertIsNone(lookup.find_by_name(""))


class CodeLookupTests(unittest.TestCase):
    def test_get_raises_for_unknown_code(self):
        with self.assertRaises(KeyError):
            lookup.get("ZZ999")
        self.assertIsNone(lookup.find("ZZ999"))

    def test_seoul_code_folds_into_the_industry(self):
        self.assertEqual(lookup.from_seoul("CS100005").code, "I210")
        self.assertEqual(lookup.from_seoul("CS300002").code, "G204")

    def test_excluded_seoul_code_has_no_industry(self):
        self.assertIsNone(lookup.from_seoul("CS300043"))
        self.assertIsNone(lookup.from_seoul("CS999999"))

    def test_several_seoul_codes_share_one_industry(self):
        # 서울시가 우리보다 잘게 쪼개져 있어 생기는 일. 합산은 맞지만 되돌릴 수는 없다.
        codes = {lookup.from_seoul(code).code for code in ("CS100005", "CS100006", "CS100007")}
        self.assertEqual(codes, {"I210"})


class Legacy70Tests(unittest.TestCase):
    def test_one_legacy_industry_can_split(self):
        codes = [industry.code for industry in lookup.from_legacy70(33)]
        self.assertEqual(codes, ["G202", "G203", "G222"])

    def test_industry_without_seoul_route_is_still_reachable(self):
        # 개폐업이 서울시 자료로는 못 만든다고 한 업종. 우리 자료로 이어진다.
        codes = [industry.code for industry in lookup.from_legacy70(43)]
        self.assertEqual(codes, ["Q101", "Q104"])

    def test_unknown_legacy_id_returns_empty(self):
        self.assertEqual(lookup.from_legacy70(999), ())


class CategoryBridgeTests(unittest.TestCase):
    def test_as_category_passes_team_contract_validation(self):
        major, middle = lookup.as_category("I201")
        category = Category(major=major, middle=middle)
        self.assertEqual(category.major, "음식점업")
        self.assertEqual(category.middle, "한식 음식점업")

    def test_every_industry_produces_a_valid_category(self):
        from app.industries.catalog import INDUSTRIES

        for code in INDUSTRIES:
            major, middle = lookup.as_category(code)
            Category(major=major, middle=middle)


if __name__ == "__main__":
    unittest.main()
