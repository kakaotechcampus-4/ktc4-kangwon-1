"""잘못된 근거 교정과 저장 자료만 사용하는 재시도를 검사합니다."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.agents.decision.agent import DecisionContractError, evaluate
from app.db import repository
from app.db.connection import initialize
from app.mocks import mock_action, mock_agents, mock_generate, mock_resolve, mock_site
from app.schemas import AgentError, AnalysisTask, AnswerSubmission, DecisionRequest
from app.services import analysis
from app.services.settings import ExecutionSettings


class DecisionRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_correction_has_real_candidates_and_failed_paths(self):
        task = AnalysisTask(request_id="test", site=mock_site())
        request = DecisionRequest(
            request_id="test",
            address="시험",
            analyses=[await f(task) for f in mock_agents().values()],
        )
        broken = mock_generate("", "")
        broken["recommendations"][0]["evidence"][0]["path"] = "/daily_average_typo"
        calls = []

        def generate(prompt, payload):
            calls.append(json.loads(payload))
            return broken

        with self.assertRaises(DecisionContractError) as caught:
            await evaluate(request, generate=generate)
        correction = calls[1]["correction"]
        self.assertEqual(correction["invalid_path"], "/daily_average_typo")
        self.assertIn("/daily_average", [c["path"] for c in correction["candidates"]])
        self.assertEqual(len(caught.exception.failures), 2)

    async def test_retry_preserves_sources_and_failure_history(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = ExecutionSettings(db_path=Path(folder) / "db.sqlite3")
            broken = mock_generate("", "")
            broken["recommendations"][0]["evidence"][0]["path"] = "/missing"
            with self.assertRaises(DecisionContractError):
                await analysis.execute_analysis(
                    "시험",
                    settings=settings,
                    request_id="test",
                    resolve=mock_resolve,
                    agents=mock_agents(),
                    generate_action=mock_action,
                    generate=Mock(return_value=broken),
                )
            before = repository.list_agent_results("test", db_path=settings.db_path)
            failed = repository.get_request("test", db_path=settings.db_path)
            self.assertTrue(hasattr(analysis, "retry_decision"), "최종판단 재시도 필요")
            with patch(
                "app.services.analysis.run_react", side_effect=AssertionError("분석 재실행 금지")
            ):
                result = await analysis.retry_decision(
                    "test",
                    failed_at=failed["completed_at"],
                    settings=settings,
                    generate=mock_generate,
                )
            self.assertEqual(result.request_id, "test")
            self.assertEqual(
                repository.get_request("test", db_path=settings.db_path)["status"], "completed"
            )
            self.assertEqual(
                before, repository.list_agent_results("test", db_path=settings.db_path)
            )
            history = repository.list_decision_failures("test", db_path=settings.db_path)
            self.assertEqual(history[0]["diagnostics"][0]["invalid_path"], "/missing")
            with self.assertRaises(ValueError):
                await analysis.retry_decision(
                    "test",
                    failed_at=failed["completed_at"],
                    settings=settings,
                    generate=mock_generate,
                )

    async def test_second_failure_and_concurrent_claim_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = ExecutionSettings(db_path=Path(folder) / "db.sqlite3")
            initialize(settings.db_path)
            repository.create_request("test", "시험", radius_m=500, db_path=settings.db_path)
            repository.mark_running("test", db_path=settings.db_path)
            task = AnalysisTask(request_id="test", site=mock_site())
            repository.save_site(task, db_path=settings.db_path)
            for fn in mock_agents().values():
                repository.save_agent(await fn(task), db_path=settings.db_path)
            repository.fail_request(
                "test",
                AgentError(code="ANALYSIS_FAILED", message="이전 실패"),
                db_path=settings.db_path,
            )
            failed_at = repository.get_request("test", db_path=settings.db_path)["completed_at"]
            entered, release = asyncio.Event(), asyncio.Event()

            async def broken(prompt, payload):
                entered.set()
                await release.wait()
                result = mock_generate(prompt, payload)
                result["recommendations"][0]["evidence"][0]["path"] = "/missing"
                return result

            first = asyncio.create_task(
                analysis.retry_decision(
                    "test", failed_at=failed_at, settings=settings, generate=broken
                )
            )
            await asyncio.wait_for(entered.wait(), 5)
            try:
                with self.assertRaises(repository.DecisionRetryConflictError):
                    await analysis.retry_decision(
                        "test", failed_at=failed_at, settings=settings, generate=mock_generate
                    )
            finally:
                release.set()
            with self.assertRaises(DecisionContractError):
                await first
            self.assertEqual(
                len(repository.list_decision_failures("test", db_path=settings.db_path)), 2
            )
            self.assertEqual(repository.list_decision_results("test", db_path=settings.db_path), [])

    async def test_retry_restores_answers_and_map_without_reexecution(self):
        from app.api.v1.mock import interactive_decision, map_observation

        with tempfile.TemporaryDirectory() as folder:
            settings = ExecutionSettings(db_path=Path(folder) / "db.sqlite3")
            waiting = await analysis.execute_analysis(
                "시험",
                settings=settings,
                request_id="test",
                resolve=mock_resolve,
                agents=mock_agents(),
                generate_action=mock_action,
                generate=interactive_decision(with_map=True, allow_questions=True),
                map_lookup=map_observation,
                allow_questions=True,
            )
            with self.assertRaises(RuntimeError):
                await analysis.resume_analysis(
                    AnswerSubmission(
                        request_id="test", question_set_id=waiting.question_set_id, answers=[]
                    ),
                    settings=settings,
                    generate=Mock(side_effect=RuntimeError("실패")),
                )
            failed = repository.get_request("test", db_path=settings.db_path)
            seen = []

            def generate(prompt, payload):
                seen.append(json.loads(payload))
                return mock_generate(prompt, payload)

            result = await analysis.retry_decision(
                "test", failed_at=failed["completed_at"], settings=settings, generate=generate
            )
            self.assertIsNotNone(result.map_observation)
            self.assertTrue(seen[0]["user_answers"])
            self.assertNotIn("question_fields", seen[0])

    async def test_correction_timeout_retains_first_diagnostic(self):
        task = AnalysisTask(request_id="test", site=mock_site())
        request = DecisionRequest(
            request_id="test",
            address="시험",
            analyses=[await fn(task) for fn in mock_agents().values()],
        )
        broken = mock_generate("", "")
        broken["recommendations"][0]["evidence"][0]["path"] = "/missing"
        with self.assertRaises(TimeoutError) as caught:
            await evaluate(request, generate=Mock(side_effect=[broken, TimeoutError()]))
        self.assertEqual(caught.exception.failures[0]["invalid_path"], "/missing")
