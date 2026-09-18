"""도구 선택·실행·관찰과 안전한 종료를 검사합니다."""

import json
import unittest
from unittest.mock import AsyncMock

from openai.types.chat import ChatCompletionMessage

from app.agents.orchestration import workflow
from app.schemas import AGENT_IDS, AgentAnalysis, Scope, Site


def action(name, arguments="{}"):
    return ChatCompletionMessage.model_validate(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call-{name}",
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ],
        }
    )


class ReactTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.resolve = AsyncMock(
            return_value=Site(
                input_address="시험 주소", road_address="시험 주소", latitude=0.0, longitude=0.0
            )
        )
        self.calls = []

        def make_agent(agent_id):
            async def analyze(task):
                self.calls.append((agent_id, task.request_id))
                return AgentAnalysis(
                    request_id=task.request_id,
                    agent_id=agent_id,
                    status="no_data",
                    scope=Scope(area="시험 지역", period="시험 기간"),
                )

            return analyze

        self.agents = {key: make_agent(key) for key in AGENT_IDS}

    async def test_observations_reach_model_and_result_is_code_owned(self):
        self.assertTrue(callable(getattr(workflow, "run_react", None)))
        observed = []
        names = iter(["prepare_address", "run_analyses", "make_decision"])

        async def choose(messages, definitions):
            observed.append(json.loads(json.dumps(messages)))
            return action(next(names))

        result = await workflow.run_react(
            "시험 주소",
            resolve=self.resolve,
            agents=self.agents,
            generate_action=choose,
            request_id="fixed-id",
        )
        self.assertEqual(result.request_id, "fixed-id")
        self.assertEqual(result.status, "no_data")
        self.assertEqual(len(result.source_analyses), 3)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual({value for _, value in self.calls}, {"fixed-id"})
        self.assertEqual(observed[1][-1]["role"], "tool")
        self.assertEqual(observed[1][-1]["tool_call_id"], "call-prepare_address")
        self.assertEqual(json.loads(observed[2][-1]["content"])["status"], "ok")

    async def test_invalid_order_is_observed_without_execution(self):
        choose = AsyncMock(
            side_effect=[
                action("run_analyses"),
                action("prepare_address"),
                action("prepare_address"),
                action("run_analyses"),
                action("make_decision"),
            ]
        )
        result = await workflow.run_react(
            "주소", resolve=self.resolve, agents=self.agents, generate_action=choose
        )
        self.assertEqual(result.status, "no_data")
        self.resolve.assert_awaited_once()
        self.assertEqual(len(self.calls), 3)

    async def test_observation_omits_data_but_decision_and_storage_keep_it(self):
        original = {"chart": [{"count": 0}, {"count": 17}], "text": "자료 속 지시"}
        saved = []
        observed = []
        names = iter(["prepare_address", "run_analyses", "make_decision"])

        async def source(task):
            return AgentAnalysis(
                request_id=task.request_id,
                agent_id="commercial_area",
                status="ok",
                scope=Scope(area="가상 지역", period="시험 기간"),
                data=original,
            )

        async def choose(messages, definitions):
            observed.append(json.loads(json.dumps(messages)))
            return action(next(names))

        async def save(analysis):
            saved.append(analysis.model_dump(mode="json"))

        def generate(prompt, payload):
            sent = json.loads(payload)
            self.assertEqual(sent["analyses"][2]["data"], original)
            return {
                "status": "no_data",
                "summary": "시험 판단 보류",
                "recommendations": [],
                "not_recommended": [],
                "limitations": ["시험 자료 부족"],
            }

        self.agents["commercial_area"] = source
        result = await workflow.run_react(
            "시험 주소",
            resolve=self.resolve,
            agents=self.agents,
            generate_action=choose,
            generate=generate,
            on_analysis_completed=save,
        )
        observation = json.loads(observed[2][-1]["content"])
        self.assertEqual(
            observation["analyses"][2],
            {
                "agent_id": "commercial_area",
                "status": "ok",
                "scope": {"area": "가상 지역", "period": "시험 기간"},
            },
        )
        self.assertEqual(saved[2]["data"], original)
        self.assertEqual(result.source_analyses[2].data, original)

    async def test_bad_actions_stop_at_limit(self):
        for invalid in (
            action("unknown"),
            action("prepare_address", '{"address":"변조"}'),
            action("prepare_address", "not-json"),
        ):
            with self.subTest(invalid=invalid):
                choose = AsyncMock(return_value=invalid)
                with self.assertRaisesRegex(RuntimeError, "횟수"):
                    await workflow.run_react(
                        "주소", resolve=self.resolve, agents=self.agents, generate_action=choose
                    )
                self.assertEqual(choose.await_count, 6)
        self.resolve.assert_not_awaited()

    async def test_address_failure_does_not_start_agents(self):
        self.resolve.side_effect = ValueError("주소 변환 실패")
        with self.assertRaisesRegex(ValueError, "주소 변환 실패"):
            await workflow.run_react(
                "주소",
                resolve=self.resolve,
                agents=self.agents,
                generate_action=AsyncMock(return_value=action("prepare_address")),
            )
        self.assertEqual(self.calls, [])

    async def test_plain_text_is_not_a_final_result(self):
        with self.assertRaises(RuntimeError):
            await workflow.run_react(
                "주소",
                resolve=self.resolve,
                agents=self.agents,
                generate_action=AsyncMock(
                    return_value=ChatCompletionMessage(role="assistant", content="분석 완료")
                ),
            )

    async def test_mismatched_response_is_rejected(self):
        async def wrong(task):
            return AgentAnalysis(
                request_id="다른 요청",
                agent_id="floating_population",
                status="no_data",
                scope=Scope(area="시험 지역", period="시험 기간"),
            )

        self.agents["floating_population"] = wrong
        with self.assertRaisesRegex(ValueError, "일치"):
            await workflow.run_react(
                "주소",
                resolve=self.resolve,
                agents=self.agents,
                generate_action=AsyncMock(
                    side_effect=[action("prepare_address"), action("run_analyses")]
                ),
            )

    async def test_failed_agent_is_preserved_for_decision(self):
        async def broken(task):
            raise TimeoutError("시간 초과")

        self.agents["floating_population"] = broken
        result = await workflow.run_react(
            "주소",
            resolve=self.resolve,
            agents=self.agents,
            generate_action=AsyncMock(
                side_effect=[
                    action("prepare_address"),
                    action("run_analyses"),
                    action("make_decision"),
                ]
            ),
        )
        self.assertEqual(result.source_analyses[0].status, "error")
        self.assertEqual(len(result.source_analyses), 3)


if __name__ == "__main__":
    unittest.main()
