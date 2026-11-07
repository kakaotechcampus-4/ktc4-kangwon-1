"""전체 업종 L과 보고서 제출의 분리 계약을 검증합니다."""

import unittest

from pydantic import ValidationError

from app.ai import tool_contracts as tools
from app.domain import contracts as c
from app.domain.schemas import DecisionRequest


class LStageContractTests(unittest.TestCase):
    def test_l_submission_is_separate_and_validates_rows_in_handler(self):
        self.assertIn("submit_l", tools.TOOL_INPUTS)
        self.assertEqual(len(tools.tool_definitions()), 10)
        self.assertNotIn("L_records", c.ReportProposal.model_fields)
        self.assertTrue(tools.SubmitLInput(L_records=[], finish=True).finish)
        self.assertEqual(len(tools.SubmitLInput(L_records=[{}] * 51).L_records), 51)
        with self.assertRaises(ValidationError):
            tools.SubmitLInput(L_records=[])
        with self.assertRaises(ValidationError):
            tools.SubmitDraftInput(phase="draft", report={"L_records": []})

    def test_all_industries_have_same_selection_contract(self):
        value = {
            "basis": "all_industries",
            "code_score_snapshot_id": "scores",
            "code_lower_rank": 51,
            "reason": "전체 업종 동일 검토",
        }
        c.LSelection.model_validate(value)
        with self.assertRaises(ValidationError):
            c.LSelection.model_validate(value | {"basis": "code_lower_top10"})
        self.assertEqual(DecisionRequest.model_fields["tool_contract_version"].default, "3")

    def test_simple_row_has_no_model_grade_and_neutral_requires_evidence(self):
        tools.LInput(industry_code="I201", note="확인한 새 조건 없음")
        tools.LInput(industry_code="I201", neutral=True, fact_ids=["1234abcd"])
        for extra in ({"grade": 3}, {"status": "observed"}, {"note": "가" * 81}):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                tools.LInput.model_validate({"industry_code": "I201"} | extra)
        with self.assertRaises(ValidationError):
            tools.LInput(industry_code="I201", neutral=True)
        with self.assertRaises(ValidationError):
            tools.LInput(
                industry_code="I201",
                neutral=True,
                fact_ids=["1234abcd"],
                factors=[{"fact_id": "1234abcd", "direction": "favorable"}],
            )

    def test_only_common_fit_allows_bulk_industry_lookup(self):
        tools.GetFactsInput(source="industry_profile", metrics=["space_fit"], limit=51)
        with self.assertRaises(ValidationError):
            tools.GetFactsInput(source="commercial_area", metrics=["density_per_km2"])
        with self.assertRaises(ValidationError):
            tools.GetFactsInput(
                source="industry_profile", metrics=["space_fit"], fact_ids=["f_bad"]
            )
