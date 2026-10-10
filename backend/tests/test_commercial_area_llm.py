"""계산된 요약의 표시 문장을 검사합니다."""

import unittest

from app.agents.commercial_area.summary import render_summary_text


class SummaryRenderingTests(unittest.TestCase):
    def test_render_text_includes_index_notes(self):
        text = render_summary_text(
            {
                "radius_notes": [],
                "overall": "종합",
                "concentration": None,
                "index_notes": [{"path": "/x", "label": "업종 다양성", "text": "사실상 17종"}],
            }
        )
        self.assertIn("업종 다양성: 사실상 17종", text)

    def test_render_text_uses_labels(self):
        text = render_summary_text(
            {
                "radius_notes": [{"radius_m": 50, "text": "점포 14개."}],
                "overall": "종합",
                "concentration": "집적 설명",
            }
        )
        self.assertIn("50m: 점포 14개.", text)
        self.assertIn("종합 평가:", text)
        self.assertIn("집적도·특화도 평가:", text)


if __name__ == "__main__":
    unittest.main()
