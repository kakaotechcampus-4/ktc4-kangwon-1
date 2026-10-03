"""평가자 공통 입력의 보존·색인 재사용·자료 갱신을 검사합니다."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from test_evaluators_agent import sample

from app.agents.evaluators.agent import prepare_evaluation_inputs
from app.agents.orchestration.nodes.evaluation import evaluate_draft_node
from app.agents.specialists.tools import fallback_brief
from app.evidence import SourceIndex
from app.mocks import mock_site
from app.schemas import EVALUATOR_IDS, AnalysisTask


class EvaluationIndexReuseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.request, self.draft = await sample()

    async def test_payload_matches_fixed_pre_refactor_baseline(self):
        expected = json.loads(
            (Path(__file__).parent / "fixtures/evaluation_input_baseline.json").read_text(
                encoding="utf-8"
            )
        )
        prepared = prepare_evaluation_inputs(self.request, self.draft, ["none", "ask_specialists"])
        self.assertEqual(prepared.payload, expected)

    async def test_four_evaluators_build_each_source_once(self):
        deps = SimpleNamespace(
            request_id=self.request.request_id,
            address=self.request.address,
            map_lookup=None,
            supplements=[],
            mode="multi_agent",
            retry_only=False,
            allow_questions=False,
            agent_timeout=1,
            step=AsyncMock(),
            generate_evaluators={
                role: AsyncMock(return_value={"verdict": "agree", "comments": []})
                for role in EVALUATOR_IDS
            },
            hooks=SimpleNamespace(on_evaluation=None),
        )
        state = {
            "outcome": self.draft,
            "analyses": self.request.analyses,
            "map_done": False,
            "supplement_done": False,
            "consult_round": 0,
        }
        with patch.object(SourceIndex, "build", wraps=SourceIndex.build) as build:
            result = await evaluate_draft_node(state, deps=deps)
        self.assertEqual(build.call_count, len(self.request.analyses))
        self.assertEqual(len(result["evaluations"]), 4)
        self.assertTrue(all(item.source == "model" for item in result["evaluations"]))

    async def test_updated_sources_receive_new_indexes_and_values(self):
        before = prepare_evaluation_inputs(self.request, self.draft, ["none"])
        source = next(a for a in self.request.analyses if a.agent_id == "commercial_area")
        source.data["store_total"] = 999
        after = prepare_evaluation_inputs(self.request, self.draft, ["none"])
        old = next(
            r.value for r in before.indexes["commercial_area"].records if r.path == "/store_total"
        )
        new = next(
            r.value for r in after.indexes["commercial_area"].records if r.path == "/store_total"
        )
        self.assertNotEqual(old, new)
        self.assertEqual(new, 999)

    async def test_fallback_reuses_one_source_index(self):
        source = next(a for a in self.request.analyses if a.agent_id == "commercial_area")
        with patch.object(SourceIndex, "build", wraps=SourceIndex.build) as build:
            brief = fallback_brief(AnalysisTask(request_id="test", site=mock_site()), source)
        self.assertTrue(brief.findings)
        self.assertEqual(build.call_count, 1)
