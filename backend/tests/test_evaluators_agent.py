"""실제 네트워크 없이 평가자 입력·응답·실패 경계를 확인합니다."""

import asyncio
import importlib
import json
import unittest
from unittest.mock import patch

from app.agents.decision.agent import evaluate
from app.mocks import mock_agents, mock_generate, mock_site
from app.schemas import AnalysisTask, DecisionRequest


async def sample():
    task = AnalysisTask(request_id="test", site=mock_site())
    request = DecisionRequest(
        request_id=task.request_id,
        address=task.site.input_address,
        analyses=[await fn(task) for fn in mock_agents().values()],
    )
    return request, await evaluate(request, generate=mock_generate)


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.network = patch("socket.socket.connect", side_effect=AssertionError("네트워크 금지"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.agent = importlib.import_module("app.agents.evaluators.agent")
        self.request, self.draft = await sample()

    async def test_input_and_response(self):
        data = self.agent.evaluation_input(self.request, self.draft, ["none"])
        self.assertEqual(set(data["draft"]), {"summary", "recommendations", "not_recommended"})
        self.assertEqual({r["code"] for r in data["industry_digest"]}, {"I201", "I212"})
        self.assertIsNone(data["map_context"])
        raw = {
            "verdict": "conditional",
            "comments": [
                {
                    "index": 9,
                    "industry_code": "I201",
                    "comment": "확인",
                    "request": "ask_user",
                    "evidence": [
                        {"agent_id": "commercial_area", "path": path}
                        for path in ("/by_middle/0/count", "/by_middle/1/count", "/missing")
                    ],
                },
                {"comment": ""},
                {"industry_code": "INVALID", "comment": "확인"},
                *[{"comment": "확인"}] * 5,
            ],
        }
        result = self.agent.check_comments(
            raw, self.request, ["none"], request_id="test", evaluator="founder"
        )
        self.assertEqual([c.index for c in result.comments], [0, 1])
        self.assertEqual(result.comments[0].request, "none")
        self.assertEqual([e.path for e in result.comments[0].evidence], ["/by_middle/0/count"])
        self.assertIn("형식 오류 지적 2개 제외", result.notes)
        raw["comments"] = [{"comment": str(i)} for i in range(5)]
        result = self.agent.check_comments(
            raw, self.request, ["none"], request_id="test", evaluator="founder"
        )
        self.assertEqual([c.comment for c in result.comments], ["0", "1", "2", "3"])

    async def test_failures_and_timeout(self):
        async def fail(*args):
            raise RuntimeError("내부 정보")

        async def slow(*args):
            await asyncio.sleep(1)

        for fn, note in ((fail, "평가 실패"), (slow, "시간 초과")):
            result = await self.agent.evaluate_draft(
                "founder",
                self.request,
                self.draft,
                generate=fn,
                allowed=["none"],
                timeout=0.01 if fn is slow else 1,
            )
            self.assertEqual(result.source, "failed")
            self.assertEqual(result.notes, [note])

        async def storage(*args):
            raise OSError("저장 실패")

        with self.assertRaises(OSError):
            await self.agent.evaluate_draft(
                "founder", self.request, self.draft, generate=storage, allowed=["none"], timeout=1
            )

    async def test_persona_and_invalid_shapes(self):
        async def generate(prompt, payload):
            self.assertEqual(json.loads(payload)["evaluator"], "customer")
            return {"verdict": "agree", "comments": "잘못된 목록"}

        result = await self.agent.evaluate_draft(
            "customer", self.request, self.draft, generate=generate, allowed=["none"], timeout=1
        )
        self.assertEqual(result.source, "model")
        self.assertEqual(result.comments, [])
        for raw in ([], {"verdict": "unknown"}):
            result = self.agent.check_comments(
                raw, self.request, ["none"], request_id="test", evaluator="founder"
            )
            self.assertEqual(result.source, "failed")
