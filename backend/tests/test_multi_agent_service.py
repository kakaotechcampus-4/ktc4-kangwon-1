"""저장된 전문가 자료와 호출 예산으로 질문 이후 실행을 재개합니다."""

import asyncio
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, patch

from test_multi_agent_graph import consult_plan, expert
from test_questions import question

from app.db import repository as repo
from app.llm.budget import MAX_CALLS, BudgetExceeded, current_scope
from app.mocks import mock_agents, mock_generate, mock_resolve
from app.schemas import AGENT_IDS, AnswerSubmission, QuestionSnapshotV2
from app.services import analysis as service
from app.services.settings import ExecutionSettings


class MultiServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "flow.sqlite3"
        self.settings = ExecutionSettings(analysis_mode="multi_agent", db_path=self.path)
        self.experts = {aid: AsyncMock(side_effect=expert) for aid in (*AGENT_IDS, "map_analysis")}
        self.agents = {aid: AsyncMock(side_effect=fn) for aid, fn in mock_agents().items()}

    async def start(self, generate, **kwargs):
        return await service.execute_analysis(
            "주소",
            request_id="r",
            resolve=mock_resolve,
            agents=self.agents,
            generate=generate,
            generate_specialists=self.experts,
            settings=self.settings,
            **kwargs,
        )

    async def test_corrupt_saved_calls_never_reach_model(self):
        waiting = await self.start(
            lambda *_: {"action": "ask_user", "questions": [question()]}, allow_questions=True
        )
        execution = json.loads(repo.get_request("r", db_path=self.path)["execution_json"])
        execution["budget"] = {"used": 1, "calls": ["corrupt"]}
        # 저장 계층의 정상 쓰기 검증을 우회해 손상된 옛 자료를 재현합니다.
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "UPDATE analysis_requests SET execution_json=? WHERE request_id='r'",
                (json.dumps(execution),),
            )
        generate = AsyncMock(return_value=mock_generate("", ""))
        with self.assertRaisesRegex(ValueError, "모델 호출 예산이 올바르지 않습니다."):
            await service.resume_analysis(
                AnswerSubmission(
                    request_id="r", question_set_id=waiting.question_set_id, answers=[]
                ),
                settings=self.settings,
                generate=generate,
                generate_specialists=self.experts,
            )
        generate.assert_not_called()

    async def test_question_resume_restores_mode_without_repeating_sources(self):
        calls = []

        async def initial(prompt, raw):
            calls.append(json.loads(raw))
            return (
                consult_plan()
                if len(calls) == 1
                else {"action": "ask_user", "questions": [question()]}
            )

        waiting = await self.start(initial, allow_questions=True)
        snapshot = repo.get_question_snapshot("r", db_path=self.path)
        self.assertIsInstance(snapshot, QuestionSnapshotV2)
        self.assertEqual(snapshot.consult_round, 1)
        self.assertGreater(snapshot.elapsed_seconds, 0)
        resumed = []

        async def finish(prompt, raw):
            resumed.append(json.loads(raw))
            return consult_plan("commercial_area") if len(resumed) == 1 else mock_generate("", "")

        result = await service.resume_analysis(
            AnswerSubmission(request_id="r", question_set_id=waiting.question_set_id, answers=[]),
            settings=ExecutionSettings(db_path=self.path),
            generate=finish,
            generate_specialists=self.experts,
        )
        self.assertEqual(result.request_id, "r")
        self.assertEqual([a.await_count for a in self.agents.values()], [1, 1, 1])
        self.assertEqual(len(repo.list_agent_briefs("r", db_path=self.path)), 3)
        self.assertEqual(
            [a.round for a in repo.list_specialist_answers("r", db_path=self.path)], [1, 2]
        )
        self.assertTrue(all(p["analysis_mode"] == "multi_agent" for p in resumed))

    async def test_expert_storage_failure_is_not_success(self):
        with patch.object(
            repo, "save_agent_brief", side_effect=sqlite3.OperationalError("저장 실패")
        ):
            with self.assertRaises(sqlite3.OperationalError):
                await self.start(mock_generate)
        self.assertEqual(repo.get_request("r", db_path=self.path)["status"], "failed")
        self.assertEqual(len(repo.list_agent_results("r", db_path=self.path)), 3)

    async def test_parallel_requests_keep_separate_budgets(self):
        async def run(request_id, count):
            async def finish(*_):
                for _ in range(count):
                    await current_scope()[0].reserve("decision", final=True)
                    await asyncio.sleep(0)
                return mock_generate("", "")

            return await service.execute_analysis(
                "주소",
                request_id=request_id,
                resolve=mock_resolve,
                agents=mock_agents(),
                generate=finish,
                generate_specialists=self.experts,
                settings=self.settings,
            )

        # 초기화 경쟁과 실행 중 예산 격리는 별도로 검사합니다.
        from app.db.connection import initialize

        initialize(self.path)
        results = await asyncio.gather(run("a", 2), run("b", 3))
        self.assertEqual({r.request_id for r in results}, {"a", "b"})
        self.assertEqual(
            [
                repo.get_deliberation(key, db_path=self.path)["execution"]["budget"]["used"]
                for key in ("a", "b")
            ],
            [2, 3],
        )

    async def test_all_expert_failures_use_fallback_without_discarding_sources(self):
        async def unavailable(*_):
            raise RuntimeError("모델 연결 실패")

        self.experts = dict.fromkeys((*AGENT_IDS, "map_analysis"), unavailable)
        result = await self.start(mock_generate)
        self.assertEqual(result.status, "partial")
        self.assertEqual(len(result.source_analyses), 3)
        self.assertEqual(
            {b.source for b in repo.list_agent_briefs("r", db_path=self.path)}, {"fallback"}
        )

    async def test_resume_exhausted_time_never_calls_model(self):
        waiting = await self.start(
            lambda *_: {"action": "ask_user", "questions": [question()]}, allow_questions=True
        )
        finish = AsyncMock(return_value=mock_generate("", ""))
        with self.assertRaises(TimeoutError):
            await service.resume_analysis(
                AnswerSubmission(
                    request_id="r", question_set_id=waiting.question_set_id, answers=[]
                ),
                settings=self.settings,
                generate=finish,
                overall_timeout=0.001,
                generate_specialists=self.experts,
            )
        finish.assert_not_called()

    async def test_resume_preserves_budget_and_does_not_reset_active_time(self):
        async def ask(*_):
            budget = current_scope()[0]
            self.assertIsNotNone(budget)
            for _ in range(budget.limit - budget.used):
                await budget.reserve("decision", final=True)
            return {"action": "ask_user", "questions": [question()]}

        waiting = await self.start(ask, allow_questions=True)

        async def finish(*_):
            await current_scope()[0].reserve("decision", final=True)
            return mock_generate("", "")

        with self.assertRaises(BudgetExceeded):
            await service.resume_analysis(
                AnswerSubmission(
                    request_id="r", question_set_id=waiting.question_set_id, answers=[]
                ),
                settings=ExecutionSettings(db_path=self.path),
                generate=finish,
                generate_specialists=self.experts,
            )
        row = repo.get_request("r", db_path=self.path)
        self.assertEqual(json.loads(row["execution_json"])["budget"]["used"], MAX_CALLS)
        self.assertEqual(json.loads(row["error_json"])["code"], "LLM_BUDGET_EXHAUSTED")
