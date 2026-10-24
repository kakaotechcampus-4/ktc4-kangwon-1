"""공간 조건 때문에 Top 5에서 뺀 업종 목록을 검증합니다."""

import unittest

from pydantic import ValidationError

from app.agentic.contracts import ConditionExcludedCandidate
from app.agentic.report import condition_excluded


def row(code, name, lower, *, excluded=False, regulation="해당 없음", reasons=()):
    return {
        "code": code,
        "name": name,
        "lower": lower,
        "coverage": 0.9,
        "regulation": regulation,
        "space": {
            "excluded": excluded,
            "exclusion_reasons": list(reasons),
            "adjustment": 0,
            "notes": [],
        },
    }


class ConditionExcludedTests(unittest.TestCase):
    def test_finalize_lists_condition_excluded(self):
        rows = [
            row("G204", "종합 소매", 80),
            row("I201", "한식 음식점", 70, excluded=True, reasons=["배기(덕트) 설치 불가"]),
            row("I101", "일반·생활 숙박", 99, regulation="금지"),
            row("S203", "자동차 수리·세차", 50, excluded=True, reasons=["1층이 아님"]),
        ]
        self.assertEqual(
            condition_excluded(rows),
            [
                ConditionExcludedCandidate(
                    industry_code="I201",
                    industry_name="한식 음식점",
                    reasons=["배기(덕트) 설치 불가"],
                    score_rank=2,
                ),
                ConditionExcludedCandidate(
                    industry_code="S203",
                    industry_name="자동차 수리·세차",
                    reasons=["1층이 아님"],
                    score_rank=3,
                ),
            ],
        )

    def test_condition_excluded_empty_without_input(self):
        rows = [row("G204", "종합 소매", 80), row("I201", "한식 음식점", 70)]
        self.assertEqual(condition_excluded(rows), [])
        legacy = [{k: v for k, v in r.items() if k != "space"} for r in rows]
        self.assertEqual(condition_excluded(legacy), [])

    def test_candidate_needs_reason_and_positive_rank(self):
        for fields in ({"reasons": [], "score_rank": 1}, {"reasons": ["이유"], "score_rank": 0}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                ConditionExcludedCandidate(
                    industry_code="I201", industry_name="한식 음식점", **fields
                )
