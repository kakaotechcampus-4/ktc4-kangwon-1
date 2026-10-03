"""전문가가 등록 도구만 제한 횟수로 실행하고 원자료를 인용하는지 확인합니다."""

import importlib.util
import json
import unittest

from app.mocks import mock_site
from app.schemas import AgentAnalysis, AnalysisTask, Scope, SpecialistQuery


def tool_message(name, arguments):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


class SpecialistTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("app.agents.specialists.agent"))
        from app.agents.specialists.agent import answer_query, write_brief

        self.write, self.answer = write_brief, answer_query
        self.task = AnalysisTask(request_id="r", site=mock_site())
        self.source = AgentAnalysis(
            request_id="r",
            agent_id="commercial_area",
            status="ok",
            scope=Scope(area="반경", period="분기"),
            data={"store_total": 7},
        )

    async def test_valid_brief_uses_code_owned_identity(self):
        async def generate(messages, definitions):
            return tool_message(
                "finish",
                {
                    "headline": "주변 점포",
                    "findings": [
                        {
                            "claim": "점포 7개",
                            "signal": "context",
                            "evidence": [{"path": "/store_total"}],
                        }
                    ],
                    "limitations": [],
                },
            )

        result = await self.write(self.task, self.source, generate=generate, tools={})
        self.assertEqual(
            (result.request_id, result.agent_id, result.source), ("r", "commercial_area", "model")
        )
        self.assertEqual(result.findings[0].claim, "점포 7개")

    async def test_unknown_tool_rejected_and_loop_bounded(self):
        calls = []

        async def generate(messages, definitions):
            calls.append(messages[-1])
            return tool_message("invented", {})

        result = await self.write(self.task, self.source, generate=generate, tools={})
        self.assertEqual(len(result.tool_calls), 4)
        self.assertTrue(all(c.status == "rejected" for c in result.tool_calls))
        self.assertLessEqual(len(calls), 5)
        self.assertEqual(result.source, "fallback")

    async def test_fallback_preserves_exclusion_warnings_and_tool_records(self):
        responses = iter(
            [
                tool_message("invented", {}),
                tool_message(
                    "finish",
                    {
                        "headline": "제외될 주장",
                        "findings": [
                            {
                                "claim": "점포 999개",
                                "signal": "context",
                                "evidence": [{"path": "/store_total"}],
                            },
                            {},
                        ],
                    },
                ),
            ]
        )

        async def generate(messages, definitions):
            return next(responses)

        result = await self.write(self.task, self.source, generate=generate, tools={})
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.tool_calls[0].tool, "invented")
        self.assertIn("전문가 근거 제외: 2번 형식 오류", result.limitations)
        self.assertIn(
            "전문가 근거 제외: 1번 수치·단위 불일치 (맞지 않는 수: 999)", result.limitations
        )

    async def test_model_failure_does_not_invent_an_answer(self):
        async def fail(messages, definitions):
            raise RuntimeError("외부 모델 실패")

        query = SpecialistQuery(
            agent_id="commercial_area", question="경쟁?", why_needed="판단", expected_impact="순위"
        )
        answer = await self.answer(
            self.task, query, 1, analysis=self.source, observation=None, generate=fail, tools={}
        )
        self.assertEqual(answer.status, "unavailable")
        self.assertEqual(answer.findings, [])

    async def test_map_observation_does_not_replace_another_experts_source(self):
        from app.api.v1.mock import map_observation
        from app.schemas import MapLookupPlan

        seen = []

        async def generate(messages, definitions):
            seen.append(json.loads(messages[1]["content"])["facts"]["shared"][""])
            return tool_message("finish", {"headline": "확인", "findings": [], "limitations": []})

        observation = await map_observation(
            self.task,
            MapLookupPlan(
                action="map_lookup",
                queries=[
                    {
                        "kind": "infrastructure",
                        "facility_code": "SW8",
                        "why_needed": "시험",
                        "expected_impact": "시험",
                    }
                ],
            ),
        )
        query = SpecialistQuery(
            agent_id="commercial_area", question="경쟁?", why_needed="판단", expected_impact="순위"
        )
        await self.answer(
            self.task,
            query,
            1,
            analysis=self.source,
            observation=observation,
            generate=generate,
            tools={},
        )
        self.assertEqual(seen, [self.source.data])

    async def test_cancellation_is_not_a_fallback(self):
        import asyncio

        async def cancelled(messages, definitions):
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await self.write(self.task, self.source, generate=cancelled, tools={})

    async def test_tool_result_contract_error_is_not_an_argument_rejection(self):
        from pydantic import ValidationError

        from app.agents.specialists.tools import SpecialistTool

        async def generate(*_):
            return tool_message("read", {})

        async def invalid(_):
            return AgentAnalysis.model_validate({"request_id": "r"})

        with self.assertRaises(ValidationError):
            await self.write(
                self.task,
                self.source,
                generate=generate,
                tools={
                    "read": SpecialistTool(
                        {"type": "function", "function": {"name": "read"}}, invalid
                    )
                },
            )

    async def test_budget_persistence_failure_is_not_model_failure(self):
        import sqlite3

        from app.llm.budget import LLMBudget, llm_scope

        async def fail(_state):
            raise sqlite3.OperationalError("저장 실패")

        budget = LLMBudget(on_change=fail)

        async def generate(messages, definitions):
            await budget.reserve("expert", final=False)

        with llm_scope(budget, "expert"), self.assertRaises(RuntimeError):
            await self.write(self.task, self.source, generate=generate, tools={})


class StepAllotmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_last_step_offers_only_finish(self):
        from app.agents.orchestration.graph import consult_steps
        from app.agents.specialists.agent import write_brief
        from app.agents.specialists.tools import SpecialistTool

        offered = []

        async def generate(messages, definitions):
            names = [d["function"]["name"] for d in definitions]
            offered.append(names)
            if "read" in names:
                return tool_message("read", {})
            return tool_message(
                "finish",
                {
                    "headline": "점포",
                    "findings": [
                        {
                            "claim": "점포 7개",
                            "signal": "context",
                            "evidence": [{"path": "/store_total"}],
                        }
                    ],
                },
            )

        async def read(_):
            return {"ok": True}

        tool = SpecialistTool(
            definition={"type": "function", "function": {"name": "read", "parameters": {}}},
            execute=read,
        )
        source = AgentAnalysis(
            request_id="r",
            agent_id="commercial_area",
            status="ok",
            scope=Scope(area="반경", period="분기"),
            data={"store_total": 7},
        )
        task = AnalysisTask(request_id="r", site=mock_site())
        brief = await write_brief(
            task, source, generate=generate, tools={"read": tool}, max_steps=2
        )
        self.assertEqual(offered, [["finish", "read"], ["finish"]])
        self.assertEqual((brief.source, len(brief.tool_calls)), ("model", 1))
        # 지도는 검색마다 매핑 호출이 붙어 같은 몫에서 차례가 더 적습니다.
        self.assertEqual(
            [consult_steps("commercial_area", 5), consult_steps("map_analysis", 5)], [5, 3]
        )
        self.assertEqual(consult_steps("business_lifecycle", 0), 1)
