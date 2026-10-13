"""수집 대역도 기존 점포 API의 키워드 인자를 유지한다."""

import unittest
from unittest.mock import AsyncMock, patch

from app.agents.commercial_area.client import StoreClient
from app.agents.commercial_area.config import Settings
from scripts.collect_rubric_samples import AuditedStores


class RubricCollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_grid_argument_is_forwarded(self):
        stores = AuditedStores(Settings(sbiz_service_key="test"))
        with patch.object(
            StoreClient,
            "stores_in_radius",
            new_callable=AsyncMock,
            return_value=([], {"fetched": 0}),
        ) as request:
            await stores.stores_in_radius(37.5, 127.0, 2000, grid_m=250)
            request.assert_awaited_once_with(37.5, 127.0, 2000, grid_m=250)

    async def test_lifecycle_returns_agent_result_and_captures_quarterly_data(self):
        from test_industry_pipeline import raw_rows

        from app.agents.business_lifecycle.config import Settings as LifecycleSettings
        from app.agents.business_lifecycle.formatter import format_for_mediator
        from app.agents.business_lifecycle.preprocess import _aggregate_rows
        from scripts.collect_rubric_samples import run_lifecycle_pipeline

        frame = _aggregate_rows(raw_rows(), "3120240", "20244", 4)
        detail = {}
        with patch(
            "scripts.collect_rubric_samples.preprocess_business_lifecycle_data",
            new_callable=AsyncMock,
            return_value=frame,
        ):
            result = await run_lifecycle_pipeline(
                "3120240", "20244", 4, "test", "대역", LifecycleSettings(), detail
            )
        self.assertEqual(result["agent_id"], "business_lifecycle")
        self.assertIn("industry_scores", result)
        self.assertEqual(len(detail["quarters"]), 4)
        self.assertNotEqual(format_for_mediator(result).status, "error")

    def test_protection_requires_geometry_containing_the_input_point(self):
        from scripts.refresh_rubric_samples import checked_zones

        polygon = {
            "type": "Polygon",
            "coordinates": [
                [[127, 37], [127.002, 37], [127.002, 37.002], [127, 37.002], [127, 37]]
            ],
        }
        zones = [{"name": "절대보호구역", "geometry": polygon}]
        self.assertEqual(len(checked_zones(zones, 37.001, 127.001)), 1)
        self.assertEqual(checked_zones(zones, 37.003, 127.003), [])
        with self.assertRaises(ValueError):
            checked_zones([{"name": "절대보호구역"}], 1, 1)

    def test_point_outside_diagonal_edge_is_not_protected(self):
        from scripts.refresh_rubric_samples import checked_zones

        polygon = {
            "type": "Polygon",
            "coordinates": [[[127, 37], [127.001, 37.001], [127, 37.002], [127, 37]]],
        }
        self.assertEqual(checked_zones([{"geometry": polygon}], 37.00049, 127.0005), [])
