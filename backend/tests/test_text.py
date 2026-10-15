"""식별자는 허용하고 자유 문장의 측정값은 계속 거절합니다."""

import unittest

from app.text import has_digit


class TextTests(unittest.TestCase):
    def test_identifiers_are_not_measurements(self):
        for text in (
            "R104 오락 서비스가 G203보다 유리",
            "G215B와 L102 비교",
            "f_3a9c1b2d 근거",
            "{f_3a9c1b2d} 근거",
            "20262 분기 get_scorecard 조회",
        ):
            with self.subTest(text=text):
                self.assertFalse(has_digit(text))

    def test_measurements_remain_invalid(self):
        for text in (
            "유동인구 12만명",
            "폐업률 30%",
            "경쟁점 3곳",
            "R104 점포 3곳",
            "20262명",
            "f_3a9c1b2d 근거 30%",
            "XR1049",
            "유동인구 １２",
            "비율 ½",
        ):
            with self.subTest(text=text):
                self.assertTrue(has_digit(text))
