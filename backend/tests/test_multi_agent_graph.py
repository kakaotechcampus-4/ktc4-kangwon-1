"""전문가 되묻기와 기존 그래프의 분기·근거 계약을 검증합니다."""

import asyncio
import inspect
import json
import unittest

from test_specialist_agent import tool_message

from app.agents.orchestration.graph import RunHooks, run_graph
from app.evidence import scalar_records
from app.mocks import mock_agents, mock_generate, mock_resolve
from app.schemas import AGENT_IDS


async def expert(messages, definitions):
    payload = json.loads(messages[1]["content"])
    data = payload.get("analysis", {}).get("data", payload.get("data", {}))
    records = (
        [
            {"path": parent + "/" + field, "value": value, "industry_code": code}
            for code, groups in [
                (None, payload["facts"]["shared"]),
                *payload["facts"]["industries"].items(),
            ]
            for parent, fields in groups.items()
            for field, value in fields.items()
        ]
        if "facts" in payload
        else scalar_records(data)
    )
    findings = (
        [
            {
                "claim": "원자료를 확인했습니다.",
                "signal": "context",
                "industry_code": records[0]["industry_code"],
                "evidence": [{"path": records[0]["path"]}],
            }
        ]
        if records
        else []
    )
    return tool_message(
        "finish", {"headline": "분석 자료", "findings": findings, "limitations": []}
    )


def consult_plan(agent="floating_population"):
    return {
        "action": "ask_specialists",
        "queries": [
            {
                "agent_id": agent,
                "question": "수요를 확인해 주세요.",
                "why_needed": "후보 비교",
                "expected_impact": "추천 순위",
            }
        ],
    }


class MultiGraphTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.assertIn("mode", inspect.signature(run_graph).parameters)

    async def test_two_consult_rounds_keep_original_data_and_compact_input(self):
        inputs, briefs, answers = [], [], []

        async def generate(prompt, raw):
            self.assertNotIn("\n지도 추가 조회는 금지됩니다.", prompt)
            inputs.append(json.loads(raw))
            return consult_plan() if len(inputs) <= 2 else mock_generate("", "")

        async def save_brief(brief):
            briefs.append(brief)

        async def save_answer(answer):
            answers.append(answer)

        result = await run_graph(
            "주소",
            resolve=mock_resolve,
            agents=mock_agents(),
            radius_m=300,
            request_id="r",
            generate=generate,
            mode="multi_agent",
            generate_specialists=dict.fromkeys((*AGENT_IDS, "map_analysis"), expert),
            hooks=RunHooks(on_brief=save_brief, on_consult=save_answer),
        )
        self.assertEqual(len(briefs), 3)
        self.assertEqual([a.round for a in answers], [1, 2])
        self.assertEqual(result.source_analyses[2].data["store_total"], 1241)
        self.assertTrue(
            all("analyses" not in p and len(p["industry_digest"]) == 75 for p in inputs)
        )
        self.assertEqual(len(inputs[-1]["answers"]), 2)

    async def test_third_consult_is_blocked(self):
        async def generate(*_):
            return consult_plan()

        with self.assertRaises(ValueError):
            await run_graph(
                "주소",
                resolve=mock_resolve,
                agents=mock_agents(),
                radius_m=300,
                request_id="r",
                generate=generate,
                mode="multi_agent",
                generate_specialists=dict.fromkeys((*AGENT_IDS, "map_analysis"), expert),
            )

    async def test_three_briefs_and_consult_answers_run_in_parallel(self):
        counts = {"brief": 0, "answer": 0}
        gates = {key: asyncio.Event() for key in counts}
        decisions = 0

        async def concurrent(messages, definitions):
            stage = (
                "brief" if json.loads(messages[1]["content"]).get("task") == "브리핑" else "answer"
            )
            counts[stage] += 1
            if counts[stage] == 3:
                gates[stage].set()
            await gates[stage].wait()
            return await expert(messages, definitions)

        async def decide(*_):
            nonlocal decisions
            decisions += 1
            if decisions == 1:
                return {
                    "action": "ask_specialists",
                    "queries": [consult_plan(aid)["queries"][0] for aid in AGENT_IDS],
                }
            return mock_generate("", "")

        async with asyncio.timeout(5):
            await run_graph(
                "주소",
                resolve=mock_resolve,
                agents=mock_agents(),
                request_id="parallel",
                radius_m=300,
                generate=decide,
                mode="multi_agent",
                generate_specialists=dict.fromkeys(AGENT_IDS, concurrent),
            )
        self.assertEqual(counts, {"brief": 3, "answer": 3})

    async def test_single_mode_does_not_call_experts(self):
        async def forbidden(*_):
            raise AssertionError("기존 모드에서 전문가를 호출하면 안 됩니다.")

        result = await run_graph(
            "주소",
            resolve=mock_resolve,
            agents=mock_agents(),
            radius_m=300,
            request_id="r",
            generate=mock_generate,
            generate_specialists=dict.fromkeys((*AGENT_IDS, "map_analysis"), forbidden),
        )
        self.assertEqual(result.recommendations[0].category.code, "I201")
