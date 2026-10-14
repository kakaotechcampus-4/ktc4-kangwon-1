"""새 decision 루프·L 검증·질문 재개·예산 종료는 모델 대역으로 검증합니다."""

import json
import tempfile
import unittest
from pathlib import Path

from app.agents.agentic.registry import persist_report
from app.agents.agentic.scoring import WEIGHTS, result, summarize
from app.db.connection import connect, initialize
from app.db.repository import create_request
from app.schemas import Site
from app.storage.raw import capture_scope


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "db.sqlite3"
        initialize(self.path)
        create_request("loop", "시험", db_path=self.path)
        self.manager = capture_scope("loop", self.path)
        self.scope = await self.manager.__aenter__()
        self.site = Site(input_address="시험", road_address="시험", latitude=37.5, longitude=127.0)
        rows = [
            summarize(code, {key: result(key) for key in WEIGHTS}, "해당 없음")
            for code in [
                "I201",
                "I202",
                "I203",
                "I204",
                "I210",
                "I211",
                "I212",
                "G203",
                "G204",
                "G205",
                "G209",
                "G210",
                "G213",
            ]
        ]
        self.score_id = persist_report(self.scope, {"rows": rows, "top5": rows[:5]}, {}, [])

    async def asyncTearDown(self):
        await self.manager.__aexit__(None, None, None)
        self.temp.cleanup()

    def message(self, name, args):
        from openai.types.chat import ChatCompletionMessage

        return ChatCompletionMessage(
            role="assistant",
            tool_calls=[
                {
                    "id": "m1",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
                }
            ],
        )

    async def test_normal_loop_and_score_recompute(self):
        from app.agents.agentic.runtime import DecisionLoop

        names = []

        async def generate(messages, definitions, settings, receipt):
            names.append(messages)
            receipt.update(model="test", usage={"prompt_tokens": 30, "completion_tokens": 20})
            return (
                self.message("get_scorecard", {"limit": 5})
                if len(names) == 1
                else self.message(
                    "submit_draft",
                    {
                        "phase": "draft",
                        "report": {
                            "summary_segments": [
                                {"type": "text", "text": "자료를 검토한 후보입니다."}
                            ]
                        },
                    },
                )
            )

        loop = await DecisionLoop.create(self.scope, self.site, generate=generate)
        loop.state["limitations"].append("서울 밖 점포 미반영")
        output = await loop.run()
        self.assertEqual(output.status, "draft_available")
        self.assertEqual(loop.budget.used, 2)
        self.assertEqual(len(output.result.top5), 5)
        self.assertIn(
            "서울 밖 점포 미반영",
            [s.text for s in output.result.limitations_segments if s.type == "text"],
        )
        self.assertFalse(any("analyses" in str(m) or "digest" in str(m) for m in names[0]))

    async def test_invalid_arguments_return_tool_error_and_continue(self):
        from app.agents.agentic.runtime import DecisionLoop

        calls = []

        async def generate(messages, definitions, settings, receipt):
            calls.append(messages)
            return (
                self.message("query_raw", {"sql": "SELECT 1", "max_rows": 51})
                if len(calls) == 1
                else self.message("submit_draft", {"phase": "draft", "report": {}})
            )

        loop = await DecisionLoop.create(self.scope, self.site, generate=generate)
        output = await loop.run()
        self.assertEqual(output.status, "draft_available")
        self.assertIn("INVALID_ARGUMENT", json.dumps(calls[-1]))

    async def test_repeat_stops_with_code_fallback(self):
        from app.agents.agentic.runtime import DecisionLoop

        async def generate(*args):
            return self.message("get_scorecard", {"limit": 5})

        loop = await DecisionLoop.create(self.scope, self.site, generate=generate)
        output = await loop.run()
        self.assertEqual(loop.budget.used, 4)
        self.assertEqual(loop.state["no_progress"], 3)
        self.assertTrue(output.result.summary_segments)
        self.assertIn(
            "decision 판단(L)을 끝내지 못해 코드 점수만으로 정렬했습니다",
            [s.text for s in output.result.limitations_segments if s.type == "text"],
        )
        self.assertTrue(output.result.limitations_segments)

    async def test_budget_fallback_has_unknown_L(self):
        from app.agents.agentic.runtime import DecisionLoop

        loop = await DecisionLoop.create(self.scope, self.site, generate=lambda *args: None)
        loop.budget.used = 26
        output = await loop.run()
        self.assertTrue(all(r.status == "unknown" for r in output.result.L_records))
        self.assertTrue(output.result.limitations_segments)

    async def test_question_resume_keeps_budget_and_refuses_repeat(self):
        from app.agents.agentic.runtime import DecisionLoop

        async def generate(*args):
            return self.message(
                "ask_user",
                {
                    "questions": [
                        {"field": "floor", "question": "층을 알려주세요.", "reason": "입점 조건"}
                    ]
                },
            )

        loop = await DecisionLoop.create(self.scope, self.site, generate=generate)
        waiting = await loop.run()
        self.assertEqual(waiting.status, "waiting_for_input")
        used = loop.budget.used
        resumed = await DecisionLoop.resume(
            self.scope, self.site, {"floor": "지하"}, generate=generate
        )
        output = await resumed.run()
        self.assertEqual(resumed.budget.used, used + 3)
        self.assertEqual(output.status, "draft_available")
        self.assertTrue(output.result.limitations_segments)

    async def test_resume_restores_all_tools_and_answers_as_tool_reply(self):
        from app.agents.agentic.runtime import DecisionLoop

        before = []

        async def generate(messages, *args):
            before.append(json.loads(json.dumps(messages)))
            return (
                self.message("get_scorecard", {"limit": 5})
                if len(before) == 1
                else self.message(
                    "ask_user",
                    {"questions": [{"field": "floor", "question": "층?", "reason": "조건"}]},
                )
            )

        loop = await DecisionLoop.create(self.scope, self.site, generate=generate)
        await loop.run()
        stored = json.loads(json.dumps(loop.state["messages"]))
        requests = []

        async def resumed_generate(messages, *args):
            requests.append(json.loads(json.dumps(messages)))
            return self.message("submit_draft", {"phase": "draft", "report": {}})

        resumed = await DecisionLoop.resume(
            self.scope, self.site, {"floor": "1층"}, generate=resumed_generate
        )
        await resumed.run()
        messages = requests[0]
        self.assertEqual(messages[:-1], stored[:-1])
        self.assertEqual(messages[-1]["role"], "tool")
        body = json.loads(messages[-1]["content"])
        self.assertEqual(body["data"]["answers"], {"floor": "1층"})
        self.assertTrue(body["data"]["fact_ids"]["floor"].startswith("f_"))
        self.assertEqual(resumed.budget.used, loop.budget.used + 1)

    async def test_duplicate_returns_previous_response_and_loop_continues(self):
        from app.agents.agentic.runtime import DecisionLoop

        requests = []

        async def generate(messages, *args):
            requests.append(json.loads(json.dumps(messages)))
            return (
                self.message("get_scorecard", {"limit": 5})
                if len(requests) <= 2
                else self.message("submit_draft", {"phase": "draft", "report": {}})
            )

        loop = await DecisionLoop.create(self.scope, self.site, generate=generate)
        output = await loop.run()
        first = json.loads(requests[1][-1]["content"])
        repeated = json.loads(requests[2][-1]["content"])
        self.assertEqual(first["data"], repeated["data"])
        self.assertTrue(repeated["duplicate"])
        self.assertIn("이미 조회한 결과", repeated["warnings"])
        self.assertEqual(loop.budget.used, 3)
        self.assertEqual(loop.tools.shared.calls["total"], 3)
        self.assertEqual(output.status, "draft_available")

    async def test_consecutive_errors_reset_after_success(self):
        from app.agents.agentic.runtime import DecisionLoop

        requests = []

        async def generate(messages, *args):
            requests.append(messages)
            if len(requests) == 3:
                return self.message("get_scorecard", {"limit": 5})
            return self.message("query_raw", {"sql": "SELECT 1", "max_rows": 51})

        loop = await DecisionLoop.create(self.scope, self.site, generate=generate)
        result = await loop.run()
        self.assertEqual(loop.budget.used, 6)
        self.assertEqual(loop.state["no_progress"], 3)
        self.assertTrue(result.result.summary_segments)

    async def make_fact(self, metric="lq"):
        from app.agents.agentic.registry import register_fact

        response = await self.scope.record(
            source="commercial_area",
            source_type="api",
            args={},
            page="test",
            status=200,
            payload={"rows": [{"metric": metric, "value": 1.2}]},
        )
        with connect(self.path) as db:
            ref = db.execute(
                "SELECT raw_row_id FROM raw_response_rows WHERE response_id=?", (response,)
            ).fetchone()[0]
        return register_fact(
            self.scope,
            industry_code=None,
            source="commercial_area",
            metric=metric,
            value=1.2,
            unit="배수",
            status="observed",
            row_ids=[ref],
        )

    async def test_resume_preserves_regulation_and_map_cache(self):
        from app.agents.agentic.contracts import (
            MapResult,
            RegulationResult,
            ToolReply,
        )
        from app.agents.agentic.runtime import DecisionLoop

        loop = await DecisionLoop.create(self.scope, self.site)
        loop.tools.shared.regulation = RegulationResult(
            status="ok",
            queried_at="검증 시각",
            contains_verified=True,
            zones=[],
            fact_ids=[],
            industry_restrictions=[{"industry_code": "I101", "status": "금지", "scope": "whole"}],
        )
        loop.tools.shared.map_cache["cached"] = ToolReply[MapResult](
            status="ok",
            data=MapResult(observation_id="map", places=[], coverage=1, has_more=False),
        )

        async def ask(*args):
            return self.message(
                "ask_user",
                {"questions": [{"field": "floor", "question": "층은?", "reason": "상가 조건"}]},
            )

        loop.generate = ask
        await loop.run()
        resumed = await DecisionLoop.resume(self.scope, self.site, {"floor": "지상"})
        self.assertEqual(resumed.tools.shared.regulation, loop.tools.shared.regulation)
        self.assertEqual(resumed.tools.shared.map_cache, loop.tools.shared.map_cache)

    async def test_answer_fact_failure_rolls_back_question_and_marks_failed(self):
        from unittest.mock import patch

        from app.agents.agentic.contracts import AskUserInput
        from app.agents.agentic.runtime import DecisionLoop
        from app.db.repository import mark_running, save_site
        from app.schemas import AnalysisTask
        from app.services.agentic_analysis import resume_agentic_analysis

        mark_running("loop", db_path=self.path)
        save_site(AnalysisTask(request_id="loop", site=self.site, radius_m=500), db_path=self.path)
        loop = await DecisionLoop.create(self.scope, self.site)
        await loop.ask_user(
            AskUserInput(
                questions=[
                    {"field": "floor", "question": "층은?", "reason": "상가 조건"},
                ]
            )
        )
        await loop.save("waiting_for_input")
        with patch("app.agents.agentic.registry.register_fact", side_effect=OSError("저장 실패")):
            with self.assertRaises(OSError):
                await resume_agentic_analysis("loop", {"floor": "지상"}, db_path=self.path)
        with connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT status FROM agentic_questions").fetchone()[0], "waiting"
            )
            self.assertEqual(
                db.execute("SELECT status FROM analysis_requests").fetchone()[0], "failed"
            )

    async def test_L_duplicate_factors_and_grade_constraints(self):
        from copy import deepcopy

        from app.agents.agentic.runtime import DecisionLoop

        fact_id = await self.make_fact()
        loop = await DecisionLoop.create(self.scope, self.site)
        await loop.tools.execute("get_facts", {"fact_ids": [fact_id]})
        record = self.l_record(loop, loop.base_rows[0]["code"], fact_id)
        cases = []
        duplicate = deepcopy(record)
        duplicate.update(grade=4, new_factors=record["new_factors"] * 2)
        cases.append(duplicate)
        for grade in [0, 2]:
            invalid = deepcopy(record)
            invalid["grade"] = grade
            invalid["new_factors"][0]["direction"] = "adverse"
            cases.append(invalid)
        for invalid in cases:
            reply = await loop.tools.execute(
                "submit_draft", {"phase": "draft", "report": {"L_records": [invalid]}}
            )
            self.assertEqual(reply.error.code, "L_EVIDENCE_INVALID")
        record["grade"] = 0
        record["new_factors"][0].update(direction="adverse", major_constraint=True)
        reply = await loop.tools.execute(
            "submit_draft", {"phase": "draft", "report": {"L_records": [record]}}
        )
        self.assertEqual(reply.status, "ok")

    def l_record(self, loop, code, fact_id, rank=None, basis=None):
        actual_rank = next(i for i, r in enumerate(loop.base_rows, 1) if r["code"] == code)
        return {
            "industry_code": code,
            "selection": {
                "basis": basis or ("code_lower_top10" if actual_rank <= 10 else "decision_extra"),
                "code_score_snapshot_id": loop.base_id,
                "code_lower_rank": rank or actual_rank,
                "reason": "새 근거 확인",
                "reason_fact_ids": [fact_id] if actual_rank > 10 else [],
            },
            "review_state": "reviewed",
            "status": "observed",
            "grade": 3,
            "new_factors": [
                {"direction": "favorable", "claim": "새 집적 상황 해석", "fact_ids": [fact_id]}
            ],
            "checked_questions": ["새 요인이 유리한가"],
            "tool_call_ids": [loop.tools.last_call_id],
        }

    async def test_L_observed_recomputes_points_and_rank(self):
        from app.agents.agentic.runtime import DecisionLoop

        fact_id = await self.make_fact()
        loop = await DecisionLoop.create(self.scope, self.site)
        await loop.tools.execute("get_facts", {"fact_ids": [fact_id]})
        code = loop.base_rows[0]["code"]
        reply = await loop.tools.execute(
            "submit_draft",
            {"phase": "draft", "report": {"L_records": [self.l_record(loop, code, fact_id)]}},
        )
        self.assertEqual(reply.status, "ok")
        candidate = loop.done.top5[0]
        self.assertEqual(candidate.L_points, 7.5)
        self.assertEqual(candidate.B, 7.5)
        self.assertEqual(candidate.code_points, 0)

    async def test_L_rejects_missing_duplicate_and_outside(self):
        from app.agents.agentic.runtime import DecisionLoop

        for metric in ["lq", "store_count"]:
            fact_id = await self.make_fact(metric)
            loop = await DecisionLoop.create(self.scope, self.site)
            await loop.tools.execute("get_facts", {"fact_ids": [fact_id]})
            record = self.l_record(loop, loop.base_rows[0]["code"], fact_id)
            if metric == "lq":
                record.update(grade=2, new_factors=[])
            reply = await loop.tools.execute(
                "submit_draft", {"phase": "draft", "report": {"L_records": [record]}}
            )
            self.assertEqual(reply.error.code, "L_EVIDENCE_INVALID")
        fact_id = await self.make_fact()
        loop = await DecisionLoop.create(self.scope, self.site)
        await loop.tools.execute("get_facts", {"fact_ids": [fact_id]})
        record = self.l_record(loop, loop.base_rows[-1]["code"], fact_id)
        record["selection"].update(basis="outside_scope", reason_fact_ids=[])
        record.update(status="unknown", grade=None, review_state="unreviewed", new_factors=[])
        reply = await loop.tools.execute(
            "submit_draft", {"phase": "draft", "report": {"L_records": [record]}}
        )
        self.assertEqual(reply.error.code, "L_EVIDENCE_INVALID")

    async def test_extra_two_allowed_three_denied(self):
        from app.agents.agentic.runtime import DecisionLoop

        fact_id = await self.make_fact()
        loop = await DecisionLoop.create(self.scope, self.site)
        await loop.tools.execute("get_facts", {"fact_ids": [fact_id]})
        records = [self.l_record(loop, r["code"], fact_id) for r in loop.base_rows[10:13]]
        invalid = await loop.tools.execute(
            "submit_draft", {"phase": "draft", "report": {"L_records": records}}
        )
        self.assertEqual(invalid.error.code, "L_EVIDENCE_INVALID")
        valid = await loop.tools.execute(
            "submit_draft", {"phase": "draft", "report": {"L_records": records[:2]}}
        )
        self.assertEqual(valid.status, "ok")
        self.assertEqual(sum(r.status == "observed" for r in loop.done.L_records), 2)

    async def test_advisor_failure_continues_and_limit_two(self):
        from app.agents.agentic.runtime import DecisionLoop
        from app.llm.client import LLMResponseError

        fact_id = await self.make_fact()
        calls = []

        async def advisor(*args):
            raise LLMResponseError("LLM_TIMEOUT")

        async def generate(*args):
            calls.append(1)
            return (
                self.message("ask_advisor", {"question": "새 집적 상황은?", "fact_ids": [fact_id]})
                if len(calls) == 1
                else self.message("submit_draft", {"phase": "draft", "report": {}})
            )

        loop = await DecisionLoop.create(
            self.scope, self.site, generate=generate, advisor_generate=advisor
        )
        output = await loop.run()
        self.assertTrue(all(r.advisor_unavailable for r in output.result.L_records))
        loop = await DecisionLoop.create(self.scope, self.site, advisor_generate=advisor)
        for question in ["첫 자문", "둘째 자문"]:
            reply = await loop.tools.execute(
                "ask_advisor", {"question": question, "fact_ids": [fact_id]}
            )
            self.assertEqual(reply.data.status, "unavailable")
        reply = await loop.tools.execute(
            "ask_advisor", {"question": "셋째 자문", "fact_ids": [fact_id]}
        )
        self.assertEqual(reply.error.code, "BUDGET_EXCEEDED")

    async def test_numeric_sentence_rejected_and_fact_rendered(self):
        from app.agents.agentic.runtime import DecisionLoop

        fact_id = await self.make_fact()
        loop = await DecisionLoop.create(self.scope, self.site)
        reply = await loop.tools.execute(
            "submit_draft",
            {
                "phase": "draft",
                "report": {"summary_segments": [{"type": "text", "text": "지수 1.2"}]},
            },
        )
        self.assertEqual(reply.error.code, "L_EVIDENCE_INVALID")
        reply = await loop.tools.execute(
            "submit_draft",
            {
                "phase": "draft",
                "report": {
                    "summary_segments": [{"type": "fact", "fact_id": fact_id, "format": "rate"}]
                },
            },
        )
        self.assertEqual(reply.status, "ok")
        with connect(self.path) as db:
            rendered = json.loads(
                db.execute(
                    "SELECT rendered_json FROM agentic_reports ORDER BY created_at DESC LIMIT 1"
                ).fetchone()[0]
            )
        self.assertEqual(rendered["summary"], "1.20")

    async def test_service_entrypoint_without_old_decision(self):
        from app.mocks import MOCK_SCOPE
        from app.schemas import AgentAnalysis
        from app.services.agentic_analysis import execute_agentic_analysis

        async def resolve(address):
            return self.site

        agents = {}
        for key in ["floating_population", "business_lifecycle", "commercial_area"]:

            async def agent(task, key=key):
                return AgentAnalysis(
                    request_id=task.request_id,
                    agent_id=key,
                    status="no_data",
                    scope=MOCK_SCOPE,
                    data={},
                )

            agents[key] = agent

        async def generate(*args):
            return self.message("submit_draft", {"phase": "draft", "report": {}})

        outcome = await execute_agentic_analysis(
            "시험",
            db_path=self.path,
            request_id="service",
            resolve=resolve,
            agents=agents,
            generate=generate,
        )
        self.assertEqual(outcome.status, "draft_available")
        self.assertEqual(outcome.budget["used"], 1)
        with connect(self.path) as db:
            self.assertEqual(
                db.execute(
                    "SELECT status FROM analysis_requests WHERE request_id='service'"
                ).fetchone()[0],
                "completed",
            )

    async def test_advisor_reasoning_does_not_inherit_luna(self):
        from unittest.mock import patch

        from app.llm.config import LLMSettings

        with patch.dict(
            "os.environ", {"LLM_REASONING_EFFORT": "none", "ADVISOR_LLM_REASONING_EFFORT": ""}
        ):
            self.assertIsNone(LLMSettings.from_env("advisor").reasoning_effort)
            self.assertEqual(LLMSettings.from_env("decision").reasoning_effort, "none")

    async def test_budget_token_and_time_caps(self):
        from app.agents.agentic.budget import RuntimeBudget
        from app.llm.budget import BudgetExceeded

        for saved in [
            {"active_seconds": 300},
            {
                "calls": [
                    {"role": "decision", "attempt": 1, "input_tokens": 160000, "output_tokens": 0}
                ],
                "used": 1,
            },
            {
                "calls": [
                    {"role": "decision", "attempt": 1, "input_tokens": 0, "output_tokens": 24000}
                ],
                "used": 1,
            },
        ]:
            budget = RuntimeBudget(saved)
            with self.assertRaises(BudgetExceeded):
                await budget.reserve("decision", input_chars=100)

    async def test_evaluator_executors_share_budget_cache(self):
        from app.agents.agentic.runtime import DecisionLoop

        loop = await DecisionLoop.create(self.scope, self.site)
        self.assertEqual(len(loop.evaluator_executors()), 4)
        self.assertTrue(
            all(e.shared is loop.tools.shared for e in loop.evaluator_executors().values())
        )


if __name__ == "__main__":
    unittest.main()
