"""평가 반영 기록이 최종판단 계약과 교정 재시도를 침범하지 않는지 확인합니다."""

import json
import unittest
from unittest.mock import AsyncMock, patch

from app.agents.decision.agent import evaluate
from app.agents.decision.llm import generate_decision
from app.mocks import mock_generate
from app.schemas import EvaluationLogEntry
from tests.test_evaluators_agent import sample


class DecisionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.request, self.draft = await sample()
        self.evaluation = {
            "draft": {},
            "evaluations": [
                {
                    "evaluator": "founder",
                    "verdict": "conditional",
                    "comments": [{"index": i, "comment": "확인"} for i in range(4)],
                }
            ],
            "failed_evaluators": [],
        }

    async def test_individual_logs_and_transport(self):
        raw = mock_generate("", "")
        raw["evaluation_log"] = [
            {
                "evaluator": "founder",
                "index": i,
                "decision": decision,
                "reason": "원자료 확인",
                **parts,
            }
            for i, decision, parts in (
                (0, "accepted", {"applied": "반영"}),
                (1, "partial", {"applied": "반영", "dropped": "제외"}),
                (2, "rejected", {"dropped": "제외"}),
            )
        ]
        raw["evaluation_log"] += [
            raw["evaluation_log"][0],
            {
                "evaluator": "customer",
                "index": 0,
                "decision": "accepted",
                "applied": "반영",
                "reason": "확인",
            },
            {"evaluator": "founder", "index": 3, "decision": "unreviewed", "reason": "모델 문장"},
        ]
        entries = []
        with patch("app.agents.decision.llm.client.complete_json", new=AsyncMock(return_value=raw)):
            result = await evaluate(
                self.request,
                generate=generate_decision,
                evaluation=self.evaluation,
                evaluation_log=entries,
            )
        self.assertEqual(
            [e.decision for e in entries], ["accepted", "partial", "rejected", "unreviewed"]
        )
        self.assertTrue(all(isinstance(e, EvaluationLogEntry) for e in entries))
        self.assertEqual(entries[-1].reason, "판정관이 이 지적을 검토하지 않았습니다.")
        self.assertNotIn("evaluation_log", result.model_dump())

    async def test_invalid_logs_and_correction(self):
        calls = []

        def generate(prompt, payload):
            data = json.loads(payload)
            self.assertEqual(data["evaluation"], self.evaluation)
            calls.append(data)
            raw = mock_generate("", "")
            raw["evaluation_log"] = [
                {
                    "evaluator": "founder",
                    "index": 0,
                    "decision": "partial",
                    "applied": "확인",
                    "reason": "부족",
                }
            ]
            if len(calls) == 1:
                raw["recommendations"][0]["evidence"][0]["path"] = "/missing"
                raw["evaluation_log"][0] = {
                    "evaluator": "founder",
                    "index": 0,
                    "decision": "accepted",
                    "applied": "첫 시도",
                    "reason": "확인",
                }
            return raw

        entries = []
        await evaluate(
            self.request, generate=generate, evaluation=self.evaluation, evaluation_log=entries
        )
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(e.decision == "unreviewed" for e in entries))
