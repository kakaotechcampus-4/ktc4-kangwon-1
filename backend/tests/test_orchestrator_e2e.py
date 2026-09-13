"""주소 입력부터 중재 결과까지 전체 흐름을 검사합니다.

외부 호출은 전부 대역으로 바꿔 네트워크 없이 돕니다.
"""

import tempfile
import unittest
from pathlib import Path

from app.agents.commercial_area import analyze as commercial_area_analyze
from app.agents.commercial_area.client import StoreClient
from app.agents.commercial_area.config import Settings
from app.agents.commercial_area.schemas import MiddleCode, Store
from app.agents.commercial_area.upjong import write_master
from app.mocks import mock_agents, mock_generate, mock_site
from app.orchestrator import run_agents, run_analysis
from app.schemas import AnalysisTask, DecisionResult

MASTER = [
    MiddleCode(code="I201", name="한식", major_code="I2", major_name="음식점업"),
    MiddleCode(code="I212", name="커피/음료", major_code="I2", major_name="음식점업"),
]


def sample_stores():
    def make(code, name, label):
        return Store(
            store_id=f"{code}-{label}",
            name=label,
            branch_name=None,
            major_code="I2",
            major_name="음식점업",
            middle_code=code,
            middle_name=name,
            small_code=None,
            small_name=None,
            latitude=37.4748,
            longitude=127.1416,
            road_address=None,
            district_code=None,
            district_name=None,
        )

    return [make("I201", "한식", f"한식{i}") for i in range(5)] + [
        make("I212", "커피/음료", f"카페{i}") for i in range(3)
    ]


class FakeStoreClient(StoreClient):
    """HTTP 호출 없이 고정 점포 목록을 돌려줍니다."""

    def __init__(self, settings, stores):
        super().__init__(settings, client=None)
        self._stores = stores

    def _meta(self, radius_m=500):
        return {
            "total_count": len(self._stores),
            "fetched": len(self._stores),
            "truncated": False,
            "radius_m": radius_m,
            "reference_date": "20260331",
            "from_cache": False,
        }

    async def stores_in_radius(self, lat, lon, radius_m, use_cache=True, grid_m=None):
        return list(self._stores), self._meta(radius_m)

    async def stores_in_radius_with_fallback(self, lat, lon, candidates, grid_m=None):
        return list(self._stores), self._meta(candidates[0])

    async def stores_in_district(self, signgu_cd):
        return list(self._stores), self._meta()

    async def aclose(self):
        return None


def generate_from_commercial_area(system_prompt, input_json):
    """상권 자료의 실제 필드를 근거로 드는 고정 응답입니다."""
    return {
        "status": "ok",
        "summary": "한식이 가장 많고 커피·음료가 뒤를 잇습니다.",
        "recommendations": [
            {
                "category": {"major": "음식점업", "middle": "한식"},
                "score": 61,
                "reasons": ["반경 안 점포 구성에서 한식 비중이 가장 큽니다."],
                "evidence": [{"agent_id": "commercial_area", "path": "/store_total"}],
                "risks": ["같은 업종 경쟁이 이미 있습니다."],
            }
        ],
        "not_recommended": [],
        "limitations": [],
    }


class MockPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_pipeline_produces_valid_decision(self):
        result = await run_analysis(
            "서울특별시 송파구 위례광장로 120 155호",
            site=mock_site(),
            agents=mock_agents(),
            generate=mock_generate,
        )
        DecisionResult.model_validate(result.model_dump())
        self.assertEqual(result.agent_id, "decision")
        self.assertEqual(len(result.source_analyses), 3)
        self.assertEqual(result.recommendations[0].category.middle, "한식 음식점업")
        self.assertEqual(result.not_recommended[0].category.middle, "커피·음료업")

    async def test_one_broken_agent_does_not_stop_the_rest(self):
        async def broken(task):
            raise TimeoutError("응답 없음")

        def generate_without_floating_population(system_prompt, input_json):
            content = mock_generate(system_prompt, input_json)
            for item in content["recommendations"] + content["not_recommended"]:
                item["evidence"] = [
                    row for row in item["evidence"] if row["agent_id"] != "floating_population"
                ]
            return content

        agents = mock_agents()
        agents["floating_population"] = broken
        result = await run_analysis(
            "서울특별시 송파구 위례광장로 120 155호",
            site=mock_site(),
            agents=agents,
            generate=generate_without_floating_population,
        )
        self.assertEqual(result.status, "partial")
        self.assertTrue(any("floating_population" in item for item in result.limitations))
        self.assertTrue(any("응답 없음" in item for item in result.limitations))

    async def test_agents_run_concurrently(self):
        import asyncio

        order = []

        def make(agent_id, delay):
            async def run(task):
                order.append(f"{agent_id}-start")
                await asyncio.sleep(delay)
                order.append(f"{agent_id}-end")
                return await mock_agents()[agent_id](task)

            return run

        agents = {
            "floating_population": make("floating_population", 0.05),
            "business_lifecycle": make("business_lifecycle", 0.0),
            "commercial_area": make("commercial_area", 0.0),
        }
        task = AnalysisTask(request_id="e2e-concurrent", site=mock_site())
        analyses = await run_agents(task, agents)

        self.assertEqual(len(analyses), 3)
        self.assertEqual(
            order[:3],
            [
                "floating_population-start",
                "business_lifecycle-start",
                "commercial_area-start",
            ],
        )

    async def test_empty_registry_is_rejected(self):
        task = AnalysisTask(request_id="e2e-empty", site=mock_site())
        with self.assertRaises(ValueError):
            await run_agents(task, {})


class RealAgentPipelineTests(unittest.IsolatedAsyncioTestCase):
    """실제 상권 에이전트를 통과시켜 중재까지 이어지는지 봅니다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        master_path = root / "upjong_codes.csv"
        write_master(master_path, MASTER)
        self.settings = Settings(
            cache_dir=root / "cache",
            upjong_master_path=master_path,
            sbiz_service_key="test-key",
        )

    def tearDown(self):
        self._tmp.cleanup()

    async def test_commercial_area_output_reaches_decision(self):
        client = FakeStoreClient(self.settings, sample_stores())

        async def commercial_area(task):
            return await commercial_area_analyze(task, settings=self.settings, store_client=client)

        result = await run_analysis(
            "서울특별시 송파구 위례광장로 120 155호",
            site=mock_site(),
            settings=self.settings,
            agents={"commercial_area": commercial_area},
            generate=generate_from_commercial_area,
        )

        DecisionResult.model_validate(result.model_dump())
        self.assertEqual(result.status, "partial")
        self.assertEqual(len(result.source_analyses), 1)
        self.assertEqual(result.source_analyses[0].agent_id, "commercial_area")
        self.assertEqual(result.source_analyses[0].data["store_total"], 8)
        self.assertTrue(any("분석 누락: floating_population" in i for i in result.limitations))
        self.assertTrue(any("분석 누락: business_lifecycle" in i for i in result.limitations))


if __name__ == "__main__":
    unittest.main()
