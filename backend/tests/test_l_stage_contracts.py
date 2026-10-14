"""전체 업종 L과 보고서 제출의 분리 계약을 검증합니다."""

import unittest

from pydantic import ValidationError

from app.agentic import contracts as c
from app.schemas import DecisionRequest


class LStageContractTests(unittest.TestCase):
    def test_l_submission_is_separate_and_bounded(self):
        self.assertIn("submit_l", c.TOOL_INPUTS)
        self.assertEqual(len(c.tool_definitions()), 10)
        self.assertNotIn("L_records", c.ReportProposal.model_fields)
        self.assertTrue(c.SubmitLInput(L_records=[], finish=True).finish)
        with self.assertRaises(ValidationError):
            c.SubmitLInput(L_records=[{}] * 18)
        with self.assertRaises(ValidationError):
            c.SubmitDraftInput(phase="draft", report={"L_records": []})

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
        self.assertEqual(DecisionRequest.model_fields["tool_contract_version"].default, "2")

    def test_only_common_fit_allows_bulk_industry_lookup(self):
        c.GetFactsInput(source="industry_profile", metrics=["space_fit"], limit=51)
        with self.assertRaises(ValidationError):
            c.GetFactsInput(source="commercial_area", metrics=["density_per_km2"])
        with self.assertRaises(ValidationError):
            c.GetFactsInput(source="industry_profile", metrics=["space_fit"], fact_ids=["f_bad"])
