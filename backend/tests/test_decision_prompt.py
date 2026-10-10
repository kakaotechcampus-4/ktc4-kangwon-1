import unittest
from importlib.resources import files

from app.evidence.citations import render_cited

PROMPT = files("app.agents.decision").joinpath("prompt.md").read_text(encoding="utf-8")
REF = ("business_lifecycle", "/industries/0/metrics/recent_year_close_rate")
SOURCES = {"business_lifecycle": {"industries": [{"metrics": {"recent_year_close_rate": 5.1}}]}}


class DecisionPromptTests(unittest.TestCase):
    def test_rate_period_wording_passes_number_check(self):
        for phrase in ("최근 네 분기의 석 달 평균 폐업률", "최근 열두 분기의 석 달 평균 폐업률"):
            self.assertIn(phrase, PROMPT)
            rendered = render_cited(f"{phrase}은 {{0}}입니다.", [REF], SOURCES)
            self.assertIn("5.1", rendered)
        self.assertNotIn("최근 1년(4개 분기)", PROMPT)
        self.assertNotIn('"최근 12개 분기의', PROMPT)

    def test_reasons_and_risks_share_one_numbered_evidence_list(self):
        for phrase in (
            "reasons와 risks는 그 항목의 evidence 배열 하나를 같이 씁니다",
            "문장마다 0부터 다시 세지 않고",
            "risks에만 쓰는 값도 같은 evidence 배열에 추가",
            '"evidence" 키는 한 번만',
        ):
            self.assertIn(phrase, PROMPT)


if __name__ == "__main__":
    unittest.main()
