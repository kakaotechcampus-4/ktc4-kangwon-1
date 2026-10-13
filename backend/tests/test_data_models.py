import unittest

from app.agents.data_models import industry_owners, parse_data
from app.evidence import resolve_pointer
from app.industries import lookup
from app.mocks import (
    mock_business_lifecycle_data,
    mock_commercial_area_data,
    mock_floating_population_data,
)
from app.schemas import MapData


def map_data():
    industry = lookup.get("I201")
    return MapData.model_validate(
        {
            "queries": {
                "q1": {
                    "request": {
                        "kind": "industry",
                        "industry_code": "I201",
                        "query": "한식",
                        "why_needed": "경쟁 확인",
                        "expected_impact": "추천 조정",
                    },
                    "status": "ok",
                    "method": "keyword",
                    "total_count": 2,
                    "place_ids": ["p1", "p2"],
                }
            },
            "places": {
                "p1": {
                    "name": "가",
                    "category_name": "음식점",
                    "mapping_status": "mapped",
                    "industry_code": "I201",
                    "mapping_method": "llm",
                },
                "p2": {"name": "나", "category_name": "음식점", "mapping_status": "unmapped"},
            },
            "industries": {
                "I201": {
                    "name": industry.name,
                    "major": industry.major_name,
                    "place_ids": ["p1"],
                    "sampled_count": 1,
                }
            },
        }
    ).model_dump(mode="json")


class OwnerTests(unittest.TestCase):
    def assert_rows_owned(self, data, owners, key):
        self.assertTrue(owners)
        for path, code in owners.items():
            self.assertEqual(resolve_pointer(data, path)[key], code)

    def test_commercial_rows(self):
        data = mock_commercial_area_data()
        owners = industry_owners("commercial_area", data)
        self.assertIn("/by_middle/0", owners)
        self.assert_rows_owned(data, owners, "code")

    def test_commercial_supplement_block_rows(self):
        data = mock_commercial_area_data()
        data["supplement_lq"] = {
            "analysis_radius_m": 500,
            "baseline_radius_m": 2000,
            "baseline_store_total": 9000,
            "checked_at": "2026-10-03T00:00:00+00:00",
            "baseline_reference_date": None,
            "from_cache": False,
            "industries": [
                {"industry_id": "I201", "citable": {"lq": True}, "lq": 1.1},
                {"industry_id": "I212", "citable": {"lq": True}, "lq": None},
            ],
            "note": "보완",
        }
        owners = industry_owners("commercial_area", data)
        self.assertEqual(owners["/supplement_lq/industries/1"], "I212")

    def test_lifecycle_rows_and_supplement_block(self):
        data = mock_business_lifecycle_data(with_supplement=True)
        owners = industry_owners("business_lifecycle", data)
        self.assertIn("/supplement_quarters/industries/0", owners)
        self.assert_rows_owned(data, owners, "industry_id")

    def test_map_industries_and_mapped_places(self):
        self.assertEqual(
            industry_owners("map_analysis", map_data()),
            {"/industries/I201": "I201", "/places/p1": "I201"},
        )

    def test_population_has_no_rows_even_when_blocks_are_removed(self):
        self.assertEqual(industry_owners("floating_population", {"description": "선별본"}), {})
        parse_data("floating_population", mock_floating_population_data())


class MockDecisionTests(unittest.TestCase):
    def test_mock_decision_without_input_cites_mock_agent_paths(self):
        from app.mocks import mock_generate

        content = mock_generate("", "")
        sources = {
            "commercial_area": mock_commercial_area_data(),
            "business_lifecycle": mock_business_lifecycle_data(),
        }
        for item in content["recommendations"] + content["not_recommended"]:
            for evidence in item["evidence"]:
                self.assertIsNotNone(
                    resolve_pointer(sources[evidence["agent_id"]], evidence["path"])
                )


if __name__ == "__main__":
    unittest.main()
