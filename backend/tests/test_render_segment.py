"""문장 조각의 fact 값을 사람이 읽는 글자로 바꾸는지 확인합니다."""

import json
import unittest
from types import SimpleNamespace

from app.agentic.report import join_segments, render_segment


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

    def test_space_fit_reads_as_korean_without_not_applicable(self):
        value = {
            "area": "일치",
            "confidence": "low",
            "floor": "해당 없음",
            "kitchen": "해당 없음",
            "reviewed": True,
            "ventilation": "미확인",
            "water_supply": "불일치",
        }
        rendered = render_segment(text_segment(), {"f": fact("space_fit", value)})
        self.assertEqual(
            rendered, "면적 일치 · 배기(덕트) 미확인 · 급배수 불일치 (비교 신뢰도 낮음)"
        )

    def test_other_objects_do_not_leak_raw_values(self):
        rendered = render_segment(text_segment(), {"f": fact("age_share", {"20": 0.3})})
        self.assertEqual(rendered, "확인 불가")


class JoinSegmentsTests(unittest.TestCase):
    def test_spaces_after_sentence_end_and_between_facts(self):
        segments = [
            SimpleNamespace(type="text", text="후보군입니다."),
            SimpleNamespace(type="fact", fact_id="a", format="text"),
            SimpleNamespace(type="fact", fact_id="b", format="text"),
        ]
        facts = {"a": fact("exclusive_area", "85㎡"), "b": fact("floor", "1층")}
        self.assertEqual(join_segments(segments, facts), "후보군입니다. 85㎡ 1층")

    def test_keeps_numbers_attached_inside_a_sentence(self):
        segments = [
            SimpleNamespace(type="text", text="점포는 "),
            SimpleNamespace(type="fact", fact_id="a", format="count"),
            SimpleNamespace(type="text", text="곳입니다."),
        ]
        facts = {"a": fact("store_total", 1200)}
        self.assertEqual(join_segments(segments, facts), "점포는 1,200곳입니다.")

    def test_spaces_after_a_space_fit_phrase(self):
        segments = [
            SimpleNamespace(type="text", text="낮습니다."),
            SimpleNamespace(type="fact", fact_id="a", format="text"),
            SimpleNamespace(type="text", text="학원을 찾는"),
        ]
        facts = {"a": fact("space_fit", {"area": "일치", "confidence": "low"})}
        self.assertEqual(
            join_segments(segments, facts), "낮습니다. 면적 일치 (비교 신뢰도 낮음) 학원을 찾는"
        )
