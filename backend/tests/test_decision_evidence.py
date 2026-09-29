"""업종과 근거 위치를 코드로 연결하는지 검사합니다."""

import json
import unittest
from unittest.mock import Mock

from app.agents.decision.agent import DecisionContractError, evaluate
from app.mocks import mock_agents, mock_generate, mock_site
from app.schemas import AnalysisTask, DecisionRequest


class EvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        task = AnalysisTask(request_id="evidence", site=mock_site())
        self.request = DecisionRequest(
            request_id=task.request_id,
            address="시험",
            analyses=[await fn(task) for fn in mock_agents().values()],
        )
        self.source = next(s for s in self.request.analyses if s.agent_id == "business_lifecycle")
        self.source.data = {
            "industries": [
                {"industry_id": "S209", "industry_name": "세탁업", "metrics": {"net": 3}},
                {
                    "industry_id": "I201",
                    "industry_name": "한식 음식점업",
                    "data_available": True,
                    "metrics": {"net": 0, "missing": None},
                },
            ]
        }

    def response(self, path, agent_id="business_lifecycle"):
        result = mock_generate("", "")
        result["not_recommended"] = []
        result["recommendations"][0]["evidence"] = [{"agent_id": agent_id, "path": path}]
        return result

    async def test_first_call_provides_exact_paths_after_reordering(self):
        original = self.request.model_dump()
        seen = []

        def generate(prompt, payload):
            seen.append(json.loads(payload))
            return self.response("/industries/1/metrics/net")

        await evaluate(self.request, generate=generate)
        entries = seen[0].get("industry_evidence", [])
        self.assertTrue(entries, "첫 호출부터 업종별 실제 근거 경로가 필요합니다.")
        entry = next(
            e
            for e in entries
            if e["industry_code"] == "I201" and e["agent_id"] == "business_lifecycle"
        )
        self.assertIn("/industries/1/metrics/net", entry["paths"])
        self.assertNotIn("/industries/1/metrics/missing", entry["paths"])
        self.assertEqual(self.request.model_dump(), original)
        self.source.data["industries"].reverse()
        await evaluate(
            self.request, generate=Mock(return_value=self.response("/industries/0/metrics/net"))
        )

    async def test_other_industry_is_rejected_and_correction_stays_in_industry(self):
        calls = []

        def generate(prompt, payload):
            calls.append(json.loads(payload))
            return self.response("/industries/0/metrics/net")

        with self.assertRaises(DecisionContractError):
            await evaluate(self.request, generate=generate)
        candidates = calls[1]["correction"]["candidates"]
        self.assertTrue(candidates)
        self.assertTrue(
            all(
                c["path"] == "/industries/1" or c["path"].startswith("/industries/1/")
                for c in candidates
            )
        )

    async def test_missing_row_and_parent_collection_are_not_evidence(self):
        self.source.data["industries"][1]["data_available"] = False
        for path in ("/industries/1", "/industries/1/metrics/net", "/industries"):
            with self.subTest(path=path), self.assertRaises(DecisionContractError):
                await evaluate(self.request, generate=Mock(return_value=self.response(path)))

    async def test_commercial_code_and_supplement_paths_match_industry(self):
        source = next(s for s in self.request.analyses if s.agent_id == "commercial_area")
        source.data = {
            "by_middle": [{"code": "S209", "count": 3}, {"code": "I201", "count": 0}],
            "supplement_lq": {"industries": [{"industry_id": "I201", "lq": 0}]},
        }
        for path in ("/by_middle/1/count", "/supplement_lq/industries/0/lq"):
            result = await evaluate(
                self.request, generate=Mock(return_value=self.response(path, "commercial_area"))
            )
            self.assertTrue(result.recommendations)
        with self.assertRaises(DecisionContractError):
            await evaluate(
                self.request,
                generate=Mock(return_value=self.response("/by_middle/0/count", "commercial_area")),
            )

    async def test_unknown_or_conflicting_identity_is_not_shared_evidence(self):
        for changes in (
            {"industry_id": "unknown"},
            {"industry_name": "세탁업"},
            {"confidence": "none"},
        ):
            original = self.source.data["industries"][1].copy()
            self.source.data["industries"][1].update(changes)
            with self.subTest(changes=changes), self.assertRaises(DecisionContractError):
                await evaluate(
                    self.request,
                    generate=Mock(return_value=self.response("/industries/1/metrics/net")),
                )
            self.source.data["industries"][1] = original

    async def test_hidden_population_block_is_not_evidence(self):
        source = next(s for s in self.request.analyses if s.agent_id == "floating_population")
        source.data.update(selection={"applied": True, "included": []}, trade_areas=[{"count": 3}])
        with self.assertRaises(DecisionContractError):
            await evaluate(
                self.request,
                generate=Mock(
                    return_value=self.response("/trade_areas/0/count", "floating_population")
                ),
            )

    async def test_area_and_major_codes_remain_shared_context(self):
        source = next(s for s in self.request.analyses if s.agent_id == "commercial_area")
        source.data = {
            "trade_areas": [{"code": "3110001", "name": "시험 상권", "area": 100}],
            "by_major": [{"code": "I2", "name": "음식점업", "count": 50}],
            "by_middle": [{"code": "unknown", "name": "미확정", "count": 3}],
        }
        for path in ("/trade_areas/0/area", "/by_major/0/count"):
            result = await evaluate(
                self.request, generate=Mock(return_value=self.response(path, "commercial_area"))
            )
            self.assertTrue(result.recommendations)
        with self.assertRaises(DecisionContractError):
            await evaluate(
                self.request,
                generate=Mock(return_value=self.response("/by_middle/0/count", "commercial_area")),
            )
