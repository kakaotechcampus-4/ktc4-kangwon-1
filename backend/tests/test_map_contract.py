"""지도 요청 경계를 검증합니다."""

import unittest

from pydantic import ValidationError

from app import schemas


def plan_data():
    return {
        "action": "map_lookup",
        "queries": [
            {
                "kind": "industry",
                "industry_code": "SV026",
                "query": "카페",
                "why_needed": "현재 경쟁 확인",
                "expected_impact": "후보 비교",
            }
        ],
    }


class MapContractTests(unittest.TestCase):
    def test_query_boundaries(self):
        self.assertTrue(hasattr(schemas, "MapLookupPlan"))
        plan = schemas.MapLookupPlan.model_validate(plan_data())
        self.assertEqual(plan.queries[0].industry_code, "SV026")
        for update in (
            {"industry_code": "bad"},
            {"query": "가" * 51},
            {"facility_code": "SW8"},
            {"query": " "},
        ):
            raw = plan_data()
            raw["queries"][0].update(update)
            with self.subTest(update=update), self.assertRaises(ValidationError):
                schemas.MapLookupPlan.model_validate(raw)
        raw = plan_data()
        raw["queries"] *= 6
        with self.assertRaises(ValidationError):
            schemas.MapLookupPlan.model_validate(raw)

    def test_failed_query_is_not_zero(self):
        self.assertTrue(hasattr(schemas, "MapQueryResult"))
        with self.assertRaises(ValidationError):
            schemas.MapQueryResult(
                request=schemas.MapLookupPlan.model_validate(plan_data()).queries[0],
                status="error",
                method="keyword",
                total_count=0,
                error="TIMEOUT",
            )

    def test_unmapped_cannot_claim_industry(self):
        self.assertTrue(hasattr(schemas, "MapPlace"))
        with self.assertRaises(ValidationError):
            schemas.MapPlace(
                name="가게", category_name="기타", mapping_status="ambiguous", industry_code="SV026"
            )

    def test_observation_rejects_inconsistent_status_and_time(self):
        from test_map_mapping import plan, task

        from app.agents.map_analysis.agent import failed_observation

        observed = failed_observation(task(), plan(), "TIMEOUT")
        for change in ({"status": "ok"}, {"queried_at": "yesterday"}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                schemas.MapObservation.model_validate({**observed.model_dump(), **change})
