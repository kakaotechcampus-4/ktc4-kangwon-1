"""평가·저장·재개를 네트워크 없이 끝까지 검증합니다."""

import asyncio
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.agents.orchestration.graph import RunHooks, run_graph
from app.api.v1.mock import specialist
from app.db import repository as repo
from app.llm.budget import LLMBudget, llm_scope
from app.mocks import mock_agents, mock_generate, mock_resolve
from app.schemas import AGENT_IDS, EVALUATOR_IDS, AnswerSubmission
from app.services.analysis import execute_analysis, resume_analysis
from app.services.settings import ExecutionSettings


async def opinion(prompt, payload):
    return {
        "verdict": "conditional",
        "comments": [{"comment": "설비 확인 필요", "request": "ask_user"}],
    }


class FlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "flow.sqlite3"
        self.network = patch("socket.socket.connect", side_effect=AssertionError("네트워크 금지"))
        self.network.start()
        self.addCleanup(self.network.stop)

    async def start(self, mode, generate, **kwargs):
        self.evaluators = {role: AsyncMock(side_effect=opinion) for role in EVALUATOR_IDS}
        return await execute_analysis(
            "주소",
            request_id="r",
            resolve=mock_resolve,
            agents=mock_agents(),
            generate=generate,
            generate_evaluators=self.evaluators,
            generate_specialists=dict.fromkeys(AGENT_IDS, specialist),
            settings=ExecutionSettings(
                analysis_mode=mode, evaluators_enabled=True, db_path=self.path
            ),
            **kwargs,
        )

    async def test_both_modes_save_and_resume(self):
        for mode in ("single_decision", "multi_agent"):
            self.path = self.path.with_name(mode + ".sqlite3")
            calls = []

            def generate(prompt, payload, calls=calls):
                data = json.loads(payload)
                calls.append(data)
                if "evaluation" in data:
                    return {
                        "action": "ask_user",
                        "questions": [
                            {
                                "field": "floor",
                                "text": "몇 층인가요?",
                                "why_needed": "접근성",
                                "expected_impact": "순위",
                            }
                        ],
                    }
                self.assertNotIn("question_fields", data)
                return mock_generate("", "")

            waiting = await self.start(mode, generate, allow_questions=True)
            self.assertEqual([fn.await_count for fn in self.evaluators.values()], [1] * 4)
            saved = repo.get_evaluation("r", db_path=self.path)
            self.assertEqual(len(saved["evaluations"]), 4)
            resumed = []

            def finish(prompt, payload, resumed=resumed):
                resumed.append(json.loads(payload))
                return mock_generate("", "")

            await resume_analysis(
                AnswerSubmission(
                    request_id="r", question_set_id=waiting.question_set_id, answers=[]
                ),
                settings=ExecutionSettings(db_path=self.path),
                generate=finish,
                generate_specialists=dict.fromkeys(AGENT_IDS, specialist),
            )
            self.assertIn("evaluation", resumed[0])
            self.assertEqual(len(repo.get_evaluation("r", db_path=self.path)["log"]), 4)
            self.assertEqual([fn.await_count for fn in self.evaluators.values()], [1] * 4)
            with self.assertRaises(ValueError):
                repo.save_evaluation_log("r", [], db_path=self.path)

    async def test_skip_no_data(self):
        result = await self.start(
            "single_decision",
            lambda *_: {
                "status": "no_data",
                "summary": "자료 없음",
                "recommendations": [],
                "not_recommended": [],
                "limitations": ["자료가 부족합니다."],
            },
        )
        self.assertEqual(result.status, "no_data")
        self.assertEqual([fn.await_count for fn in self.evaluators.values()], [0] * 4)
        self.assertEqual(
            json.loads(repo.get_request("r", db_path=self.path)["execution_json"])[
                "evaluation_skipped"
            ],
            "no_data",
        )

    async def test_final_four_rounds_after_two_draft_rounds(self):
        calls = []

        def generate(prompt, payload):
            data = json.loads(payload)
            calls.append(data)
            if data["specialists"]:
                return {
                    "action": "ask_specialists",
                    "queries": [
                        {
                            "agent_id": "commercial_area",
                            "question": "확인",
                            "why_needed": "경쟁",
                            "expected_impact": "순위",
                        }
                    ],
                }
            return mock_generate("", "")

        await self.start("multi_agent", generate)
        self.assertEqual(
            [a.round for a in repo.list_specialist_answers("r", db_path=self.path)],
            list(range(1, 7)),
        )
        self.assertEqual(
            [p["limits"]["remaining_consult_rounds"] for p in calls if "evaluation" in p],
            [4, 3, 2, 1, 0],
        )
        self.assertEqual([fn.await_count for fn in self.evaluators.values()], [1] * 4)

    async def test_no_final_for_agree_or_all_failed(self):
        for fail in (False, True):

            async def reviewer(*_, fail=fail):
                if fail:
                    raise RuntimeError("실패")
                return {"verdict": "agree", "comments": []}

            calls, events = [], []

            def generate(prompt, payload, calls=calls):
                calls.append(json.loads(payload))
                return mock_generate("", "")

            async def step(stage, event, detail, events=events):
                events.append((stage, event, detail))

            result = await run_graph(
                "주소",
                request_id="r",
                radius_m=500,
                resolve=mock_resolve,
                agents=mock_agents(),
                generate=generate,
                evaluators_enabled=True,
                generate_evaluators=dict.fromkeys(EVALUATOR_IDS, reviewer),
                hooks=RunHooks(on_step=step),
            )
            self.assertEqual(len(calls), 1)
            self.assertFalse(events[-1][2]["final_call"])
            self.assertFalse(any("평가" in value for value in result.limitations))

    async def test_one_failed_evaluator_does_not_stop_other_opinions(self):
        captured = []

        async def fail(*_):
            raise RuntimeError("모델 실패")

        async def save(draft, evaluations):
            captured.extend(evaluations)

        generators = dict.fromkeys(EVALUATOR_IDS, opinion)
        generators["examiner"] = fail
        result = await run_graph(
            "주소",
            request_id="r",
            radius_m=500,
            resolve=mock_resolve,
            agents=mock_agents(),
            generate=mock_generate,
            evaluators_enabled=True,
            generate_evaluators=generators,
            hooks=RunHooks(on_evaluation=save),
        )
        self.assertEqual([e.source for e in captured], ["failed", "model", "model", "model"])
        self.assertFalse(any("평가" in value for value in result.limitations))
        resolver = AsyncMock(side_effect=mock_resolve)
        with self.assertRaises(ValueError):
            await run_graph(
                "주소",
                request_id="r",
                radius_m=500,
                resolve=resolver,
                agents=mock_agents(),
                evaluators_enabled=True,
                generate_evaluators={"founder": opinion},
            )
        resolver.assert_not_awaited()

    async def test_budget_skip_and_reserve(self):
        evaluator = AsyncMock(side_effect=opinion)
        events = []

        async def step(stage, event, detail):
            events.append((stage, event, detail))

        with llm_scope(LLMBudget(limit=8, used=3), "decision", final=True):
            await run_graph(
                "주소",
                request_id="r",
                radius_m=500,
                resolve=mock_resolve,
                agents=mock_agents(),
                generate=mock_generate,
                evaluators_enabled=True,
                generate_evaluators=dict.fromkeys(EVALUATOR_IDS, evaluator),
                hooks=RunHooks(on_step=step),
            )
        evaluator.assert_not_awaited()
        self.assertEqual(events[-1], ("evaluate", "completed", {"skipped": "budget"}))
        budget = LLMBudget(limit=10, used=4)
        payloads = []

        def generate(prompt, payload):
            payloads.append(json.loads(payload))
            return mock_generate("", "")

        with llm_scope(budget, "decision", final=True):
            await run_graph(
                "주소",
                request_id="r",
                radius_m=500,
                resolve=mock_resolve,
                agents=mock_agents(),
                generate=generate,
                mode="multi_agent",
                generate_specialists=dict.fromkeys(AGENT_IDS, specialist),
                evaluators_enabled=True,
                generate_evaluators=dict.fromkeys(EVALUATOR_IDS, evaluator),
            )
        self.assertEqual(payloads[0]["specialists"], [])
        self.assertEqual(evaluator.await_count, 4)

    async def test_storage_atomicity_duplicate_and_upsert(self):
        from app.db.connection import connect, initialize
        from app.schemas import Evaluation, EvaluationLogEntry
        from tests.test_evaluators_agent import sample

        request, draft = await sample()
        initialize(self.path)
        repo.create_request(request.request_id, request.address, db_path=self.path)
        repo.mark_running(request.request_id, db_path=self.path)
        entries = [
            Evaluation(
                request_id=request.request_id, evaluator=role, source="model", verdict="agree"
            )
            for role in EVALUATOR_IDS
        ]
        with connect(self.path) as db:
            db.execute(
                "CREATE TRIGGER fail_evaluation BEFORE INSERT ON evaluations "
                "WHEN NEW.evaluator_id='customer' BEGIN SELECT RAISE(ABORT, 'test'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            repo.save_evaluation(draft, entries, db_path=self.path)
        self.assertIsNone(repo.get_evaluation(request.request_id, db_path=self.path))
        with connect(self.path) as db:
            db.execute("DROP TRIGGER fail_evaluation")
        repo.save_evaluation(draft, entries, db_path=self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            repo.save_evaluation(draft, entries, db_path=self.path)
        repo.save_evaluation_log(request.request_id, [], db_path=self.path)
        logs = [
            EvaluationLogEntry(evaluator="founder", index=0, decision="unreviewed", reason="확인")
        ]
        repo.save_evaluation_log(request.request_id, logs, db_path=self.path)
        self.assertEqual(repo.get_evaluation(request.request_id, db_path=self.path)["log"], logs)

    async def test_final_map_does_not_repeat_evaluation(self):
        from app.api.v1.mock import map_observation

        calls = []

        def generate(prompt, payload):
            data = json.loads(payload)
            calls.append(data)
            if "evaluation" in data and not data.get("map_observation"):
                return {
                    "action": "map_lookup",
                    "queries": [
                        {
                            "kind": "infrastructure",
                            "facility_code": "SW8",
                            "why_needed": "접근성",
                            "expected_impact": "확인",
                        }
                    ],
                }
            return mock_generate("", "")

        await self.start("single_decision", generate, map_lookup=map_observation)
        self.assertEqual(len(calls), 3)
        self.assertEqual([fn.await_count for fn in self.evaluators.values()], [1] * 4)

    async def test_retry_reuses_saved_evaluators_and_budget(self):
        from app.llm.budget import current_scope
        from app.services.analysis import retry_decision

        async def broken(prompt, payload):
            if "evaluation" in json.loads(payload):
                for _ in range(25):
                    await current_scope()[0].reserve("decision", final=True)
                raise RuntimeError("최종판단 실패")
            return mock_generate("", "")

        with self.assertRaises(RuntimeError):
            await self.start("single_decision", broken)
        failed = repo.get_request("r", db_path=self.path)

        async def finish(prompt, payload):
            self.assertIn("evaluation", json.loads(payload))
            self.assertEqual(current_scope()[0].limit, 64)
            self.assertEqual(current_scope()[0].used, 25)
            return mock_generate("", "")

        await retry_decision(
            "r",
            failed_at=failed["completed_at"],
            settings=ExecutionSettings(db_path=self.path),
            generate=finish,
        )
        self.assertEqual([fn.await_count for fn in self.evaluators.values()], [1] * 4)
        self.assertEqual(len(repo.get_evaluation("r", db_path=self.path)["log"]), 4)

    async def test_retry_before_evaluation_restarts_draft_without_refetch(self):
        from app.services.analysis import retry_decision

        for mode in ("single_decision", "multi_agent"):
            self.path = self.path.with_name("retry_" + mode + ".sqlite3")
            with self.assertRaises(RuntimeError):
                await self.start(mode, lambda *_: (_ for _ in ()).throw(RuntimeError("초안 실패")))
            before = repo.list_agent_results("r", db_path=self.path)
            failed = repo.get_request("r", db_path=self.path)
            self.assertEqual([fn.await_count for fn in self.evaluators.values()], [0] * 4)
            calls = []

            def finish(prompt, payload, calls=calls):
                data = json.loads(payload)
                calls.append(data)
                self.assertFalse(data.get("specialists"))
                self.assertNotIn("question_fields", data)
                return mock_generate("", "")

            with patch(
                "app.services.analysis.resolve_site", side_effect=AssertionError("재조회 금지")
            ):
                result = await retry_decision(
                    "r",
                    failed_at=failed["completed_at"],
                    settings=ExecutionSettings(db_path=self.path),
                    generate=finish,
                    generate_evaluators=self.evaluators,
                )
            self.assertEqual(result.request_id, "r")
            self.assertEqual(["evaluation" in data for data in calls], [False, True])
            self.assertEqual([fn.await_count for fn in self.evaluators.values()], [1] * 4)
            self.assertEqual(before, repo.list_agent_results("r", db_path=self.path))
            self.assertEqual(len(repo.get_evaluation("r", db_path=self.path)["log"]), 4)

    async def test_corrupt_resume_and_storage_errors_propagate(self):
        from app.db.connection import connect

        def generate(prompt, payload):
            if "evaluation" in json.loads(payload):
                return {
                    "action": "ask_user",
                    "questions": [
                        {
                            "field": "floor",
                            "text": "몇 층인가요?",
                            "why_needed": "접근성",
                            "expected_impact": "순위",
                        }
                    ],
                }
            return mock_generate("", "")

        waiting = await self.start("single_decision", generate, allow_questions=True)
        with connect(self.path) as db:
            db.execute("DELETE FROM evaluations WHERE request_id='r'")
            db.execute("DELETE FROM evaluation_drafts WHERE request_id='r'")
        with self.assertRaises(ValueError):
            await resume_analysis(
                AnswerSubmission(
                    request_id="r", question_set_id=waiting.question_set_id, answers=[]
                ),
                settings=ExecutionSettings(db_path=self.path),
                generate=mock_generate,
            )
        self.path = self.path.with_name("error.sqlite3")
        with (
            patch.object(
                repo, "save_evaluation", side_effect=sqlite3.OperationalError("저장 실패")
            ),
            self.assertRaises(sqlite3.OperationalError),
        ):
            await self.start("single_decision", mock_generate)
        self.assertEqual(repo.get_request("r", db_path=self.path)["status"], "failed")

    async def test_legacy_migration_preserves_rows_and_is_repeatable(self):
        from app.db.connection import initialize
        from app.schemas import SpecialistAnswer

        schema = (
            await asyncio.to_thread(Path("app/db/schema.sql").read_text, encoding="utf-8")
        ).replace("round BETWEEN 1 AND 6", "round BETWEEN 1 AND 2")
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript(schema)
        repo.create_request("r", "주소", analysis_mode="multi_agent", db_path=self.path)
        repo.mark_running("r", db_path=self.path)
        answer = SpecialistAnswer(
            request_id="r",
            round=1,
            query={
                "agent_id": "commercial_area",
                "question": "확인",
                "why_needed": "경쟁",
                "expected_impact": "순위",
            },
            status="unavailable",
            findings=[],
        )
        repo.save_specialist_answer(answer, db_path=self.path)
        initialize(self.path)
        initialize(self.path)
        self.assertEqual(repo.list_specialist_answers("r", db_path=self.path), [answer])
        repo.save_specialist_answer(answer.model_copy(update={"round": 6}), db_path=self.path)
        self.assertEqual(
            [a.round for a in repo.list_specialist_answers("r", db_path=self.path)], [1, 6]
        )

    async def test_resume_preserves_twenty_minute_limit_after_env_toggle(self):
        from app.db.connection import connect

        def generate(prompt, payload):
            if "evaluation" in json.loads(payload):
                return {
                    "action": "ask_user",
                    "questions": [
                        {
                            "field": "floor",
                            "text": "몇 층인가요?",
                            "why_needed": "접근성",
                            "expected_impact": "순위",
                        }
                    ],
                }
            return mock_generate("", "")

        waiting = await self.start("single_decision", generate, allow_questions=True)
        with connect(self.path) as db:
            db.execute(
                "UPDATE analysis_requests SET execution_json="
                "json_set(execution_json,'$.elapsed_seconds',700) WHERE request_id='r'"
            )
        result = await resume_analysis(
            AnswerSubmission(request_id="r", question_set_id=waiting.question_set_id, answers=[]),
            settings=ExecutionSettings(db_path=self.path),
            generate=mock_generate,
        )
        self.assertEqual(result.request_id, "r")
