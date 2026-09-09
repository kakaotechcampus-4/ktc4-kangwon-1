"""모델 응답을 구조화된 요약으로 바꾸는 과정을 검사합니다."""

import unittest

from app.agents.commercial_area.geocode import query_candidates, split_detail
from app.agents.commercial_area.llm import parse_summary, render_summary_text

CLEAN = (
    '{"radius_notes":[{"radius_m":100,"text":"점포 50개."},{"radius_m":50,"text":"점포 14개."}],'
    '"overall":"생활 상권입니다.","concentration":"한식이 빽빽합니다."}'
)


class SummaryParsingTests(unittest.TestCase):
    def test_parses_json_and_sorts_by_radius(self):
        summary = parse_summary(CLEAN)
        self.assertEqual([n["radius_m"] for n in summary["radius_notes"]], [50, 100])
        self.assertEqual(summary["overall"], "생활 상권입니다.")

    def test_parses_json_wrapped_in_code_fence(self):
        self.assertEqual(len(parse_summary("```json\n" + CLEAN + "\n```")["radius_notes"]), 2)

    def test_parses_json_with_surrounding_chatter(self):
        summary = parse_summary("정리하면 다음과 같습니다.\n" + CLEAN + "\n도움이 되었길 바랍니다.")
        self.assertEqual(summary["overall"], "생활 상권입니다.")

    def test_falls_back_to_plain_text(self):
        summary = parse_summary("그냥 줄글로 답해버린 경우입니다.")
        self.assertEqual(summary["radius_notes"], [])
        self.assertEqual(summary["overall"], "그냥 줄글로 답해버린 경우입니다.")

    def test_drops_malformed_rows_only(self):
        summary = parse_summary(
            '{"radius_notes":[{"radius_m":"이상","text":"x"},{"radius_m":50,"text":"정상"},'
            '{"radius_m":100,"text":""}],"overall":null}'
        )
        self.assertEqual([n["radius_m"] for n in summary["radius_notes"]], [50])
        self.assertIsNone(summary["overall"])

    def test_empty_payload_has_no_content(self):
        summary = parse_summary('{"unrelated": 1}')
        self.assertEqual(summary["radius_notes"], [])
        self.assertIsNone(summary["overall"])

    def test_render_text_uses_labels(self):
        text = render_summary_text(parse_summary(CLEAN))
        self.assertIn("50m: 점포 14개.", text)
        self.assertIn("종합 평가:", text)
        self.assertIn("집적도·특화도 평가:", text)


class AddressSplitTests(unittest.TestCase):
    def test_splits_unit_from_road_address(self):
        self.assertEqual(
            split_detail("서울특별시 송파구 위례광장로 120 155호"),
            ("서울특별시 송파구 위례광장로 120", "155호"),
        )

    def test_keeps_address_without_unit(self):
        self.assertEqual(split_detail("서울 송파구 위례광장로 120"), ("서울 송파구 위례광장로 120", None))

    def test_candidates_get_progressively_shorter(self):
        candidates = query_candidates("서울특별시 강남구 테헤란로 123, ○○빌딩 3층 302호")
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[-1], "서울특별시 강남구 테헤란로 123")


if __name__ == "__main__":
    unittest.main()
