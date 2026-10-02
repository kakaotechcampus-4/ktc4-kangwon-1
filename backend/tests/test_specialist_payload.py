"""현 구현에서 고정한 색인과 전문가 입력 기준값을 검증합니다."""

import json
import unittest
from decimal import Decimal
from pathlib import Path

from app.agents.specialists.agent import write_brief
from app.evidence import index_paths, scalar_records
from app.evidence.findings import _radii
from app.mocks import mock_site
from app.schemas import AgentAnalysis, AnalysisTask
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
            self.assertEqual(len(payload), case["brief_payload_chars"])
