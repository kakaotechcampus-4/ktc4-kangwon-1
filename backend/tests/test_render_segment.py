"""문장 조각의 fact 값을 사람이 읽는 글자로 바꾸는지 확인합니다."""

import json
import unittest
from types import SimpleNamespace

from app.application.report import join_segments, limitation_segments, render_segment


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

    def test_no_space_before_punctuation_after_space_fit(self):
        segments = [
            SimpleNamespace(type="fact", fact_id="a", format="text"),
            SimpleNamespace(type="text", text="."),
        ]
        facts = {"a": fact("space_fit", {"area": "일치", "confidence": "low"})}
        self.assertEqual(join_segments(segments, facts), "면적 일치 (비교 신뢰도 낮음).")

    def test_other_facts_ending_in_parenthesis_stay_attached(self):
        segments = [
            SimpleNamespace(type="text", text="근처에 "),
            SimpleNamespace(type="fact", fact_id="a", format="text"),
            SimpleNamespace(type="text", text="이 있습니다."),
        ]
        facts = {"a": fact("place_name", "스타벅스(강남점)")}
        self.assertEqual(join_segments(segments, facts), "근처에 스타벅스(강남점)이 있습니다.")


class LimitationSegmentsTests(unittest.TestCase):
    def test_server_sentences_do_not_stick_to_model_text(self):
        from app.domain.contracts import TextSegment

        model = [TextSegment(type="text", text="표본이 작음")]
        segments = limitation_segments(model, ["서울 밖 점포 미반영", "검토를 마쳤습니다."])
        expected = "표본이 작음 서울 밖 점포 미반영. 검토를 마쳤습니다."
        self.assertEqual(join_segments(segments, {}).strip(), expected)

    def test_server_sentences_alone_have_no_leading_gap(self):
        segments = limitation_segments([], ["서울 밖 점포 미반영"])
        self.assertEqual([s.text for s in segments], ["서울 밖 점포 미반영."])


class StrippedTextJoinTests(unittest.TestCase):
    def test_space_before_a_number_after_stripped_text(self):
        segments = [
            SimpleNamespace(type="text", text="점포는"),
            SimpleNamespace(type="fact", fact_id="a", format="count"),
            SimpleNamespace(type="text", text="곳입니다."),
        ]
        facts = {"a": fact("store_total", 1200)}
        self.assertEqual(join_segments(segments, facts), "점포는 1,200곳입니다.")

    def test_no_space_inside_brackets(self):
        segments = [
            SimpleNamespace(type="text", text="("),
            SimpleNamespace(type="fact", fact_id="a", format="count"),
            SimpleNamespace(type="text", text=")"),
        ]
        facts = {"a": fact("store_total", 1200)}
        self.assertEqual(join_segments(segments, facts), "(1,200)")


class TextValueParityTests(unittest.TestCase):
    def render(self, value, fmt="text", unit=""):
        segment = SimpleNamespace(type="fact", fact_id="f", format=fmt)
        return render_segment(segment, {"f": fact("x", value, unit)})

    def test_lists_read_as_comma_separated(self):
        self.assertEqual(self.render(["카페", "학원"]), "카페, 학원")

    def test_whole_floats_and_booleans_read_like_the_screen(self):
        self.assertEqual(self.render(2.0), "2")
        self.assertEqual(self.render(True), "예")
        self.assertEqual(self.render(None), "확인 불가")

    def test_ties_round_away_from_zero_like_the_screen(self):
        self.assertEqual(self.render(0.0625, "percent", "비율"), "6.3%")
        self.assertEqual(self.render(12.5, "distance"), "13m")
        self.assertEqual(self.render(0.125, "rate"), "0.13")
        self.assertEqual(self.render(1.005, "rate"), "1.00")
