"""전문가의 요청 경계와 횟수 제한을 확인합니다."""

import unittest

from pydantic import ValidationError

from app import schemas


class SpecialistContractTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(schemas, "ConsultPlan"), "전문가 공통 계약이 필요합니다.")
        self.query = {
            "agent_id": "commercial_area",
            "question": "한식 점포 수를 확인해 주세요.",
            "industry_codes": ["SV020"],
            "why_needed": "경쟁 판단",
            "expected_impact": "추천 순위 검토",
        }

    def test_query_rejects_unknown_and_duplicate_industries(self):
        for codes in (["I299"], ["SV020", "SV020"]):
            with self.subTest(codes=codes), self.assertRaises(ValidationError):
                schemas.SpecialistQuery(**{**self.query, "industry_codes": codes})

    def test_plan_rejects_duplicate_specialists(self):
        with self.assertRaises(ValidationError):
            schemas.ConsultPlan(action="ask_specialists", queries=[self.query, self.query])
        plan = schemas.ConsultPlan(action="ask_specialists", queries=[self.query])
        self.assertEqual(plan.queries[0].industry_codes, ["SV020"])
        with self.assertRaises(ValidationError):
            schemas.ConsultPlan(
                action="ask_specialists",
                queries=[
                    {**self.query, "agent_id": role}
                    for role in (*schemas.AGENT_IDS, "map_analysis")
                ],
            )

    def test_answer_rejects_third_round_and_other_request(self):
        base = dict(request_id="r", round=1, query=self.query, status="unavailable", findings=[])
        with self.assertRaises(ValidationError):
            schemas.SpecialistAnswer(**{**base, "round": 3})
        analysis = dict(
            request_id="other",
            agent_id="commercial_area",
            status="error",
            error={"code": "UPSTREAM", "message": "조회 실패"},
        )
        with self.assertRaises(ValidationError):
            schemas.SpecialistAnswer(**base, analysis=analysis)

    def test_map_answer_cannot_claim_analysis_agent(self):
        analysis = dict(
            request_id="r",
            agent_id="commercial_area",
            status="error",
            error={"code": "UPSTREAM", "message": "조회 실패"},
        )
        with self.assertRaises(ValidationError):
            schemas.SpecialistAnswer(
                request_id="r",
                round=1,
                query={**self.query, "agent_id": "map_analysis"},
                status="unavailable",
                findings=[],
                analysis=analysis,
            )

    def test_finding_requires_valid_industry_and_pointer(self):
        base = dict(claim="점포가 있습니다.", signal="context", industry_code="SV020")
        for changed in (
            {"industry_code": "I299", "evidence": [{"path": "/count"}]},
            {"evidence": [{"path": "count"}]},
            {"evidence": []},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValidationError):
                schemas.Finding(**{**base, **changed})

    def test_tool_log_and_answer_have_bounded_payload(self):
        with self.assertRaises(ValidationError):
            schemas.ToolCallRecord(tool="get_summary", arguments={}, status="ok", elapsed_ms=-1)
        finding = dict(claim="확인", signal="context", evidence=[{"path": "/count"}])
        with self.assertRaises(ValidationError):
            schemas.SpecialistAnswer(
                request_id="r",
                round=1,
                query=self.query,
                status="answered",
                findings=[finding] * 6,
            )

    def test_snapshot_v2_keeps_v1_readable_and_checks_references(self):
        task = schemas.AnalysisTask(
            request_id="r",
            site=schemas.Site(
                input_address="주소",
                road_address="주소",
                latitude=37.5,
                longitude=127.0,
            ),
        )
        question = dict(
            field="floor", text="몇 층인가요?", why_needed="접근성", expected_impact="순위"
        )
        waiting = schemas.WaitingForInput(request_id="r", question_set_id="q", questions=[question])
        base = dict(
            task=task,
            waiting=waiting,
            source_attempts=dict.fromkeys(schemas.AGENT_IDS, 1),
            supplement_done=False,
            feedback=[],
        )
        self.assertEqual(schemas.QuestionSnapshot(**base).version, 1)
        new = schemas.QuestionSnapshotV2(**base, brief_agents=list(schemas.AGENT_IDS))
        self.assertEqual(new.version, 2)
        for changes in ({"llm_calls": 25}, {"consult_round": 3}, {"brief_agents": []}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                schemas.QuestionSnapshotV2.model_validate({**new.model_dump(), **changes})


if __name__ == "__main__":
    unittest.main()


class ConsultParseTests(unittest.TestCase):
    def test_duplicate_or_unknown_specialist_keeps_first_allowed_query(self):
        from app.agents.decision.agent import _parse_outcome

        def q(agent_id, text):
            return {
                "agent_id": agent_id,
                "question": text,
                "why_needed": "왜",
                "expected_impact": "영향",
            }

        plan = _parse_outcome(
            {
                "action": "ask_specialists",
                "queries": [
                    q("commercial_area", "첫"),
                    q("commercial_area", "둘"),
                    q("map_analysis", "지도"),
                ],
            },
            final_only=False,
            operations=None,
            allowed_questions=set(),
            allow_map_lookup=False,
            specialists=["commercial_area"],
        )
        self.assertEqual([x.question for x in plan.queries], ["첫"])
        with self.assertRaises(ValueError):
            _parse_outcome(
                {"action": "ask_specialists", "queries": [q("map_analysis", "지도")]},
                final_only=False,
                operations=None,
                allowed_questions=set(),
                allow_map_lookup=False,
                specialists=["commercial_area"],
            )
