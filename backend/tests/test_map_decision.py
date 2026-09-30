"""지도 요청과 근거 검증을 확인합니다."""

import unittest
from unittest.mock import AsyncMock, Mock, patch

from test_map_mapping import plan

from app.agents.decision.agent import DecisionContractError, evaluate
from app.agents.decision.llm import generate_decision
from app.agents.map_analysis.agent import failed_observation
from app.mocks import mock_agents, mock_generate, mock_site
from app.schemas import AnalysisTask, DecisionRequest, MapLookupPlan


class MapDecisionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.task = AnalysisTask(request_id="r", site=mock_site())
        self.request = DecisionRequest(
            request_id="r",
            address="시험",
            analyses=[await f(self.task) for f in mock_agents().values()],
        )

    async def test_request_only_when_enabled(self):
        result = await evaluate(
            self.request, allow_map_lookup=True, generate=Mock(return_value=plan().model_dump())
        )
        self.assertIsInstance(result, MapLookupPlan)
        with self.assertRaises(ValueError):
            await evaluate(self.request, generate=Mock(return_value=plan().model_dump()))

    async def test_parser_accepts_map_request(self):
        with patch(
            "app.agents.decision.llm.client.complete_json",
            AsyncMock(return_value=plan().model_dump()),
        ):
            result = await generate_decision("json", "{}", settings=object())
        self.assertIsInstance(result, MapLookupPlan)

    async def test_failed_observation_is_preserved_but_not_evidence(self):
        observed = failed_observation(self.task, plan(), "TIMEOUT")
        raw = self.request.model_dump()
        raw["map_observation"] = observed
        request = DecisionRequest.model_validate(raw)
        final = await evaluate(request, generate=mock_generate)
        self.assertEqual(final.map_observation, observed)
        content = mock_generate("", "")
        content["recommendations"][0]["evidence"] = [
            {"agent_id": "map_analysis", "path": "/queries/q1/total_count"}
        ]
        with self.assertRaises(DecisionContractError):
            await evaluate(request, generate=Mock(return_value=content))
