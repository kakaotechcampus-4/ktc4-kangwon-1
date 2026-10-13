"""2001fb9c 실행의 P105 관측으로 문맥 반경과 수치 경고를 검증합니다."""

import json
import unittest
from pathlib import Path

from app.agents.decision.context import build_context
from app.agents.specialists.agent import answer_query
from app.evidence import validate_findings
from app.mocks import mock_agents
from app.schemas import AnalysisTask, DecisionRequest, Finding, MapObservation, SpecialistQuery


class MapFindingRadiusTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.observation = MapObservation.model_validate_json(
            (Path(__file__).parent / "fixtures/map_2001fb9c_p105.json").read_text("utf-8")
        )
        self.data = self.observation.data.model_dump(mode="json")

    def finding(self, claim):
        return Finding(
            claim=claim,
            signal="context",
            industry_code="P105",
            evidence=[{"path": "/places/11575083/distance_m"}],
        )

    def test_observed_radius_passes_but_page_count_and_unknown_radius_fail(self):
        good = self.finding("반경 500m 안에 뉴멘토보습학원이 {0}m 거리에 있습니다.")
        page = self.finding("첫 페이지 15곳 중 뉴멘토보습학원이 {0}m 거리에 있습니다.")
        wrong = self.finding("반경 600m 안에 뉴멘토보습학원이 {0}m 거리에 있습니다.")
        kept, warnings = validate_findings(
            [good, page, wrong], agent_id="map_analysis", data=self.data, radii={500}
        )
        self.assertEqual(
            kept, [good.model_copy(update={"claim": good.claim.replace("{0}", "232")})]
        )
        self.assertIn("(맞지 않는 수: 15)", warnings[0])
        self.assertIn("(맞지 않는 수: 600)", warnings[1])
        kept, warnings = validate_findings([good], agent_id="map_analysis", data=self.data)
        self.assertEqual(kept, [])
        self.assertIn("(맞지 않는 수: 500)", warnings[0])

    def test_warning_contains_only_mismatched_numbers_up_to_three(self):
        for claim, expected in (
            ("민감문구 901, 902, 903, 904, 901 그리고 232m", "901, 902, 903"),
            ("232명", "232"),
            ("232%", "232"),
            ("232만 명", "232"),
        ):
            with self.subTest(claim=claim):
                kept, warnings = validate_findings(
                    [self.finding(claim)], agent_id="map_analysis", data=self.data
                )
                self.assertEqual(kept, [])
                self.assertEqual(
                    warnings,
                    [f"전문가 근거 제외: 1번 수치·단위 불일치 (맞지 않는 수: {expected})"],
                )

    async def test_expert_and_context_use_latest_observation_radius(self):
        finding = self.finding("반경 500m 안에 뉴멘토보습학원이 {0}m 거리에 있습니다.")
        query = SpecialistQuery(
            agent_id="map_analysis",
            question="거리 확인",
            industry_codes=["P105"],
            why_needed="경쟁 확인",
            expected_impact="판단 보완",
        )

        async def generate(messages, definitions):
            return {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "finish",
                        "type": "function",
                        "function": {
                            "name": "finish",
                            "arguments": json.dumps(
                                {
                                    "headline": "확인",
                                    "findings": [finding.model_dump()],
                                    "limitations": [],
                                }
                            ),
                        },
                    }
                ],
            }

        answer = await answer_query(
            AnalysisTask(request_id=self.observation.request_id, site=self.observation.site),
            query,
            1,
            analysis=None,
            observation=None,
            generate=generate,
            tools={},
            get_data=lambda: self.data,
            get_observation=lambda: self.observation,
        )
        self.assertEqual(answer.status, "answered")
        task = AnalysisTask(request_id=self.observation.request_id, site=self.observation.site)
        request = DecisionRequest(
            request_id=self.observation.request_id,
            address="오금로 404",
            analyses=[await agent(task) for agent in mock_agents().values()],
            map_observation=self.observation,
        )
        context = build_context(request, briefs=[], answers=[answer])
        rendered = finding.model_copy(update={"claim": finding.claim.replace("{0}", "232")})
        self.assertEqual(context["answers"][0]["findings"], [rendered.model_dump(mode="json")])

    def test_observed_radius_does_not_allow_bare_distance(self):
        finding = self.finding("반경 500m 안에 학원이 232m 거리에 있습니다.")
        kept, _ = validate_findings([finding], agent_id="map_analysis", data=self.data, radii={500})
        self.assertEqual(kept, [])
