"""새 위치용 고정 계산에 정답 라벨·미래 결제 분포가 섞이지 않도록 검증합니다."""

import unittest

from app.industries.catalog import INDUSTRY_TO_SEOUL
from backtest.purchase_profile import FIELDS, build_profiles
from backtest.support90 import validate_reference


class Support90ReferenceTests(unittest.TestCase):
    def fixture(self):
        raw = {
            "STDR_YYQU_CD": "20242",
            "MEGA_CD": "11",
            "SVC_INDUTY_CD": INDUSTRY_TO_SEOUL["G216"][0],
            **{f: 100 for fields in FIELDS.values() for f in fields.values()},
        }
        purchase = build_profiles([raw])
        reference = [
            {"area": str(i), "latitude": 37.5, "longitude": 127, "ratios": {"G216": [1.0, 1.0]}}
            for i in range(1650)
        ]
        return purchase, reference

    def test_fixed_complete_reference_is_accepted(self):
        self.assertIsNone(validate_reference(*self.fixture()))

    def test_target_labels_are_rejected_before_scoring(self):
        purchase, reference = self.fixture()
        reference[0]["target"] = "G216"
        with self.assertRaisesRegex(ValueError, "정답 라벨"):
            validate_reference(purchase, reference)

    def test_future_profiles_and_duplicate_city_areas_are_rejected(self):
        purchase, reference = self.fixture()
        purchase["G216"]["age"]["source_quarter"] = "20252"
        with self.assertRaises(ValueError):
            validate_reference(purchase, reference)
        purchase, reference = self.fixture()
        reference[-1] = reference[0]
        with self.assertRaises(ValueError):
            validate_reference(purchase, reference)

    def test_invalid_paired_ratios_are_rejected(self):
        purchase, reference = self.fixture()
        reference[0]["ratios"]["G216"] = [1, None]
        with self.assertRaises(ValueError):
            validate_reference(purchase, reference)


if __name__ == "__main__":
    unittest.main()
