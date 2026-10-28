"""문장 조각의 fact 값을 사람이 읽는 글자로 바꾸는지 확인합니다."""

import json
import unittest
from types import SimpleNamespace

from app.agentic.report import render_segment


def fact(metric, value, unit=""):
    return {"metric": metric, "value_json": json.dumps(value), "unit": unit}


def text_segment():
    return SimpleNamespace(type="fact", fact_id="f", format="text")


class RenderSegmentTests(unittest.TestCase):
    def test_confirmed_facilities_read_as_korean(self):
        value = {"ventilation": "unavailable", "kitchen": "present", "water_supply": "installable"}
        rendered = render_segment(text_segment(), {"f": fact("existing_facilities", value)})
        self.assertEqual(rendered, "주방 있음 · 배기(덕트) 설치 불가 · 급배수 설치 가능")

    def test_free_text_facilities_stay_as_written(self):
        rendered = render_segment(text_segment(), {"f": fact("existing_facilities", "배기 없음")})
        self.assertEqual(rendered, "배기 없음")
