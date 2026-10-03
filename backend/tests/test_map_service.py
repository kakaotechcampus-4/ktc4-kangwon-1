"""지도 관측 저장과 질문 재개를 실제 SQLite로 검사합니다."""

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from test_map_mapping import plan
from test_questions import question

from app.agents.map_analysis.agent import failed_observation
from app.db import repository as repo
from app.mocks import mock_agents, mock_generate, mock_resolve
from app.schemas import AnswerSubmission
from app.services import analysis as service


class MapServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_after_map_save_preserves_observation(self):
        actual = repo.complete_map_lookup
        loop = asyncio.get_running_loop()

        def cancel_after_save(*args, **kwargs):
            actual(*args, **kwargs)
            loop.call_soon_threadsafe(owner.cancel)

        with patch.object(repo, "complete_map_lookup", side_effect=cancel_after_save):
            owner = asyncio.create_task(
                self.start(Mock(side_effect=[plan(), mock_generate("", "")]))
            )
            with self.assertRaises(asyncio.CancelledError):
                await owner
        self.assertIsNotNone(repo.get_map_observation("r", db_path=self.path))
        self.assertEqual(repo.get_request("r", db_path=self.path)["status"], "failed")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "map.sqlite3"
        self.calls = 0

    async def lookup(self, task, request):
        self.calls += 1
        return failed_observation(task, request, "TIMEOUT")

    async def start(self, generate):
        return await service.execute_analysis(
            "시험",
            request_id="r",
            db_path=self.path,
            resolve=mock_resolve,
            agents=mock_agents(),
            generate=generate,
            map_lookup=self.lookup,
            allow_questions=True,
        )

    async def test_wait_resume_reuses_saved_map(self):
        waiting = await self.start(
            Mock(side_effect=[plan(), {"action": "ask_user", "questions": [question()]}])
        )
        saved = repo.get_map_observation("r", db_path=self.path)
        self.assertEqual(saved.status, "error")
        answer = AnswerSubmission(
            request_id="r", question_set_id=waiting.question_set_id, answers=[]
        )
        final = await service.resume_analysis(answer, db_path=self.path, generate=mock_generate)
        self.assertEqual(final.map_observation, saved)
        self.assertEqual(self.calls, 1)
        again = await service.resume_analysis(answer, db_path=self.path, generate=mock_generate)
        self.assertEqual(again, final)
        self.assertEqual(len(repo.list_agent_results("r", db_path=self.path)), 3)

    async def test_storage_failure_is_not_swallowed(self):
        with patch.object(repo, "complete_map_lookup", side_effect=sqlite3.OperationalError):
            with self.assertRaises(sqlite3.OperationalError):
                await self.start(Mock(side_effect=[plan(), mock_generate("", "")]))
        self.assertEqual(repo.get_request("r", db_path=self.path)["status"], "failed")

    async def test_final_failure_preserves_observation(self):
        with self.assertRaises(RuntimeError):
            await self.start(Mock(side_effect=[plan(), RuntimeError("판단 실패")]))
        self.assertIsNotNone(repo.get_map_observation("r", db_path=self.path))
        self.assertEqual(repo.get_request("r", db_path=self.path)["status"], "failed")
