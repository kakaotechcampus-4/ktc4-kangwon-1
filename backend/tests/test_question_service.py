"""질문·답변 서비스의 실제 DB 연결을 검사합니다."""

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from test_questions import question

from app.agents.orchestration.tools import SupplementTool
from app.db import repository as repo
from app.mocks import mock_agents, mock_generate, mock_resolve
from app.schemas import AnswerSubmission, SupplementOperation, WaitingForInput
from app.services import analysis as service
from app.services.settings import ExecutionSettings


class QuestionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_model_configuration_does_not_consume_answers(self):
        submission = await self.prepare()
        with self.assertRaises(ValueError):
            await service.resume_analysis(
                submission, db_path=self.path, settings=ExecutionSettings()
            )
        self.assertEqual(repo.get_request("r", db_path=self.path)["status"], "waiting_for_input")
        self.assertIsNone(repo.get_question_answers("r", db_path=self.path))

    async def test_invalid_injected_generator_does_not_consume_answers(self):
        submission = await self.prepare()
        with self.assertRaises(ValueError):
            await service.resume_analysis(submission, db_path=self.path, generate=object())
        self.assertEqual(repo.get_request("r", db_path=self.path)["status"], "waiting_for_input")
        self.assertIsNone(repo.get_question_answers("r", db_path=self.path))

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "run.sqlite3"
        self.resolve = AsyncMock(side_effect=mock_resolve)
        self.agents = {k: AsyncMock(side_effect=f) for k, f in mock_agents().items()}
        self.plan = dict(action="ask_user", questions=[question()])

    async def start(self, **changes):
        options = dict(
            db_path=self.path,
            request_id="r",
            resolve=self.resolve,
            agents=self.agents,
            generate=Mock(return_value=self.plan),
            allow_questions=True,
        )
        options.update(changes)
        return await service.execute_analysis("시험 주소", **options)

    async def prepare(self):
        waiting = await self.start()
        self.assertIsInstance(waiting, WaitingForInput)
        self.assertEqual(repo.get_request("r", db_path=self.path)["status"], "waiting_for_input")
        self.assertEqual(repo.list_decision_results("r", db_path=self.path), [])
        return AnswerSubmission(request_id="r", question_set_id=waiting.question_set_id, answers=[])

    async def test_resume_and_duplicate_do_not_repeat_analysis_or_decision(self):
        submission = await self.prepare()
        generate = Mock(side_effect=mock_generate)
        final = await service.resume_analysis(submission, db_path=self.path, generate=generate)
        again = await service.resume_analysis(submission, db_path=self.path, generate=generate)
        self.assertEqual(final, again)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(self.resolve.await_count, 1)
        self.assertEqual([a.await_count for a in self.agents.values()], [1, 1, 1])
        self.assertEqual(len(repo.list_agent_results("r", db_path=self.path)), 3)
        self.assertEqual(len(repo.list_decision_results("r", db_path=self.path)), 1)

    async def test_concurrent_duplicate_does_not_fail_owner(self):
        submission = await self.prepare()
        entered, release = asyncio.Event(), asyncio.Event()

        async def generate(prompt, payload):
            entered.set()
            await release.wait()
            return mock_generate(prompt, payload)

        task = asyncio.create_task(
            service.resume_analysis(submission, db_path=self.path, generate=generate)
        )
        try:
            await asyncio.wait_for(entered.wait(), 2)
            with self.assertRaises(service.AnalysisAlreadyRunningError):
                await service.resume_analysis(submission, db_path=self.path, generate=generate)
            self.assertEqual(repo.get_request("r", db_path=self.path)["status"], "running")
        finally:
            release.set()
            await task

    async def test_failed_resume_preserves_sources_and_answers(self):
        submission = await self.prepare()
        with self.assertRaises(RuntimeError):
            await service.resume_analysis(
                submission, db_path=self.path, generate=Mock(side_effect=RuntimeError("연결 오류"))
            )
        self.assertEqual(repo.get_request("r", db_path=self.path)["status"], "failed")
        self.assertIsNotNone(repo.get_question_answers("r", db_path=self.path))
        self.assertEqual(len(repo.list_agent_results("r", db_path=self.path)), 3)

    async def test_waiting_survives_cancel_after_save(self):
        save = repo.save_question_snapshot
        loop = asyncio.get_running_loop()

        def cancel_after_save(*args, **kwargs):
            save(*args, **kwargs)
            loop.call_soon_threadsafe(owner.cancel)

        with patch.object(repo, "save_question_snapshot", side_effect=cancel_after_save):
            owner = asyncio.create_task(self.start())
            with self.assertRaises(asyncio.CancelledError):
                await owner
        self.assertEqual(repo.get_request("r", db_path=self.path)["status"], "waiting_for_input")

    async def test_final_storage_failure_is_not_success(self):
        submission = await self.prepare()
        with patch.object(
            repo, "complete_request", side_effect=sqlite3.OperationalError("저장 실패")
        ):
            with self.assertRaises(sqlite3.OperationalError):
                await service.resume_analysis(submission, db_path=self.path, generate=mock_generate)
        self.assertEqual(repo.get_request("r", db_path=self.path)["status"], "failed")
        self.assertEqual(repo.list_decision_results("r", db_path=self.path), [])

    async def test_question_disabled_keeps_existing_result(self):
        result = await self.start(allow_questions=False, generate=mock_generate)
        self.assertNotIsInstance(result, WaitingForInput)
        self.assertIsNone(repo.get_question_snapshot("r", db_path=self.path))

    async def test_old_execution_cannot_fail_claimed_resume(self):
        actual = service.run_graph

        async def finish_then_fail(*args, **kwargs):
            waiting = await actual(*args, **kwargs)
            submission = AnswerSubmission(
                request_id="r", question_set_id=waiting.question_set_id, answers=[]
            )
            await asyncio.to_thread(repo.claim_question_resume, submission, db_path=self.path)
            raise RuntimeError("대기 반환 중 호출자 오류")

        with patch.object(service, "run_graph", side_effect=finish_then_fail):
            with self.assertRaises(RuntimeError):
                await self.start()
        self.assertEqual(repo.get_request("r", db_path=self.path)["status"], "running")

    async def test_supplement_then_question_restores_adopted_attempt(self):
        supplement = dict(
            action="supplement",
            requests=[
                dict(
                    agent_id="commercial_area",
                    operation="details",
                    decision_question="경쟁 판단",
                    missing_information="세부 자료",
                    why_needed="후보 확인",
                    expected_impact="위험 설명",
                )
            ],
        )

        async def details(task, previous):
            previous.data["detail"] = 17
            return previous

        tool = SupplementTool(
            operation=SupplementOperation(
                agent_id="commercial_area", operation="details", description="시험"
            ),
            execute=details,
            eligible=lambda task, previous: True,
        )
        waiting = await self.start(
            generate=Mock(side_effect=[supplement, self.plan]), supplements=[tool]
        )
        submission = AnswerSubmission(
            request_id="r", question_set_id=waiting.question_set_id, answers=[]
        )
        final = await service.resume_analysis(submission, db_path=self.path, generate=mock_generate)
        self.assertEqual(
            next(
                a.data["detail"] for a in final.source_analyses if a.agent_id == "commercial_area"
            ),
            17,
        )
        import json

        stored = repo.list_decision_results("r", db_path=self.path)[0]
        self.assertEqual(json.loads(stored["source_attempts_json"])["commercial_area"], 2)
