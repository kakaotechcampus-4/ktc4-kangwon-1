"""리포트에 보여 줄 전체 업종 순위와 규제 제외 목록을 검증합니다."""

import unittest

from pydantic import ValidationError

from app.application.report import industry_ranking, regulation_excluded
from app.domain.contracts import RankedIndustry, RegulationExcludedIndustry
from app.domain.scoring import rank_candidates


def row(code, name, lower, *, excluded=False, regulation="해당 없음"):
    return {
        "code": code,
        "name": name,
        "lower": lower,
        "coverage": 0.9,
        "regulation": regulation,
        "space": {"excluded": excluded, "exclusion_reasons": [], "adjustment": 0, "notes": []},
    }


ROWS = [
    row("G204", "종합 소매", 80),
    row("I201", "한식 음식점", 70, excluded=True),
    row("I101", "일반·생활 숙박", 99, regulation="금지"),
    row("S203", "자동차 수리·세차", 50),
    row("N105", "여행 서비스", 90),
    row("M103", "법무 서비스", 60, regulation="금지", excluded=True),
]


class IndustryRankingTests(unittest.TestCase):
    def test_ranking_uses_top5_rule_without_limit(self):
        ranking = industry_ranking(ROWS, excluded_codes={"S203"})
        self.assertEqual(
            ranking,
            [
                RankedIndustry(industry_code="N105", industry_name="여행 서비스", rank=1),
                RankedIndustry(industry_code="G204", industry_name="종합 소매", rank=2),
                RankedIndustry(
                    industry_code="S203",
                    industry_name="자동차 수리·세차",
                    rank=3,
                    ai_excluded=True,
                ),
            ],
        )
        self.assertEqual(
            [r.industry_code for r in ranking[:5]],
            [r["code"] for r in rank_candidates(ROWS)],
        )

    def test_regulation_excluded_lists_prohibited_once(self):
        self.assertEqual(
            regulation_excluded(ROWS),
            [
                RegulationExcludedIndustry(industry_code="I101", industry_name="일반·생활 숙박"),
                RegulationExcludedIndustry(industry_code="M103", industry_name="법무 서비스"),
            ],
        )

    def test_ranked_industry_needs_positive_rank(self):
        with self.assertRaises(ValidationError):
            RankedIndustry(industry_code="G204", industry_name="종합 소매", rank=0)


if __name__ == "__main__":
    unittest.main()
