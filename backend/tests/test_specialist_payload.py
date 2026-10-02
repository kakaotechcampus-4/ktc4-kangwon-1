"""현 구현에서 고정한 색인과 전문가 입력 기준값을 검증합니다."""

import json
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from app.agents.decision.context import build_context
from app.agents.specialists.agent import write_brief
from app.evidence import SourceIndex, can_cite, index_paths, scalar_records
from app.evidence.findings import _radii
from app.mocks import mock_site
from app.schemas import AgentAnalysis, AgentBrief, AnalysisTask, DecisionRequest
from scripts.measure_payloads import capture_payload


def baseline_cases():
    return json.loads(
        (Path(__file__).parent / "fixtures" / "specialist_index_baseline.json").read_text(
            encoding="utf-8"
        )
    )["cases"]


class IndexBaselineTests(unittest.TestCase):
    def test_four_sources_match_fixed_index_baselines(self):
        for case in baseline_cases():
            with self.subTest(source=case["name"]):
                data = case["analysis"]["data"] if "analysis" in case else case["data"]
                self.assertEqual(index_paths(data), case["owners"])
                self.assertEqual(scalar_records(data), case["records"])
                self.assertEqual(_radii(data), {Decimal(r) for r in case["radii"]})


class PayloadBaselineTests(unittest.IsolatedAsyncioTestCase):
    async def test_brief_payload_sizes_match_fixed_baselines(self):
        for case in baseline_cases():
            if "analysis" not in case:
                continue
            analysis = AgentAnalysis.model_validate(case["analysis"])
            task = AnalysisTask(request_id=analysis.request_id, site=mock_site(), radius_m=500)
            payload = await capture_payload(write_brief, task, analysis, tools={})
            limit = 1.1 if analysis.agent_id == "floating_population" else 0.5
            self.assertLessEqual(len(payload), case["brief_payload_chars"] * limit)
            self.assertNotIn("analysis", json.loads(payload))
            self.assertNotIn("industry_paths", json.loads(payload))


class SourceIndexTests(unittest.TestCase):
    def test_single_index_preserves_all_fixed_records(self):
        from app.evidence import SourceIndex

        for case in baseline_cases():
            with self.subTest(source=case["name"]):
                data = case["analysis"]["data"] if "analysis" in case else case["data"]
                with patch("app.evidence.index.resolve_pointer", side_effect=AssertionError):
                    index = SourceIndex.build(data)
                self.assertEqual(index.owners, case["owners"])
                self.assertEqual(
                    [
                        {"path": r.path, "value": r.value, "industry_code": r.owner}
                        for r in index.records
                    ],
                    case["records"],
                )
                self.assertEqual(index.radii, frozenset(Decimal(r) for r in case["radii"]))

    def test_context_builds_each_source_once_even_with_briefs(self):
        from app.evidence import SourceIndex

        analyses = [
            AgentAnalysis.model_validate(c["analysis"]) for c in baseline_cases() if "analysis" in c
        ]
        request = DecisionRequest(
            request_id=analyses[0].request_id, address="검증 주소", analyses=analyses
        )
        briefs = [
            AgentBrief(
                request_id=a.request_id,
                agent_id=a.agent_id,
                source="model",
                headline="확인",
                findings=[],
            )
            for a in analyses
        ]
        with patch.object(SourceIndex, "build", wraps=SourceIndex.build) as build:
            build_context(request, briefs=briefs, answers=[])
        self.assertEqual(build.call_count, len(analyses))
        for call, analysis in zip(build.call_args_list, request.analyses, strict=True):
            self.assertIs(call.args[0], analysis.data)


class FactsTests(unittest.TestCase):
    def test_grouped_paths_preserve_values_and_are_citable(self):
        from app.agents.specialists.facts import build_facts

        for case in baseline_cases():
            if "analysis" not in case:
                continue
            data = case["analysis"]["data"]
            index = SourceIndex.build(data)
            facts = build_facts(index)
            restored = {}
            groups = [(None, facts["shared"]), *facts["industries"].items()]
            for owner, parents in groups:
                for parent, fields in parents.items():
                    for field, value in fields.items():
                        path = parent + "/" + field
                        self.assertIsNone(can_cite(data, path, owner, indexed=index.owners))
                        restored[path] = (value, owner)
            self.assertEqual(restored, {r.path: (r.value, r.owner) for r in index.records})
