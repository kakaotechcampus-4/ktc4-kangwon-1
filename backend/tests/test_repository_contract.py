"""업무 저장 계약과 SQLite의 이력·재개 호환을 검사합니다."""

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from app.db import repository
from app.db.analysis_repository import SqliteAnalysisRepository
from app.db.connection import connect, initialize
from app.mocks import mock_agents, mock_site
from app.schemas import AnalysisTask, AnswerSubmission, DecisionResult
from app.services.analysis import execute_analysis
from app.services.mocking import mock_dependencies
from app.services.settings import ExecutionSettings
from app.storage.contracts import AnalysisRepositoryProtocol


class RecordingRepository:
    """업무 호출만 기록하는 저장소 대역입니다."""

    def __init__(self, detail):
        self.detail = detail
        self.calls = []
        self.claimed = False

    def get_detail(self, request_id):
        return self.detail if request_id == self.detail.request.request_id else None

    def complete(self, result, *, attempt, source_attempts):
        self.calls.append(("complete", attempt, source_attempts))
        self.detail = replace(
            self.detail,
            request=replace(self.detail.request, status="completed"),
            result=result.model_dump(mode="json"),
        )

    def claim_answers(self, submission):
        previous = self.claimed
        self.claimed = True
        self.calls.append(("claim_answers", submission))
        return not previous

    def load_resume(self, request_id):
        raise NotImplementedError

    def claim_retry(self, request_id, failed_at):
        raise NotImplementedError


class RepositoryContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = self.enterContext(tempfile.TemporaryDirectory())
        self.path = initialize(Path(self.folder) / "contract.sqlite3")
        self.task = AnalysisTask(request_id="contract", site=mock_site())
        repository.create_request("contract", self.task.site.input_address, db_path=self.path)
        repository.mark_running("contract", db_path=self.path)
        repository.save_site(self.task, db_path=self.path)
        self.sources = [await fn(self.task) for fn in mock_agents().values()]
        for source in self.sources:
            repository.save_agent(source, db_path=self.path)
        self.storage = SqliteAnalysisRepository(self.path)

    def result(self):
        return DecisionResult(
            schema_version="1.0",
            agent_id="decision",
            request_id="contract",
            address=self.task.site.input_address,
            status="no_data",
            summary="계약 검증",
            recommendations=[],
            not_recommended=[],
            limitations=["시험용 판단 자료 없음"],
            source_analyses=self.sources,
        )

    def test_completion_contract_with_sqlite_and_recording_repository(self):
        detail = self.storage.get_detail("contract")
        for storage in (self.storage, RecordingRepository(detail)):
            with self.subTest(storage=type(storage).__name__):
                self.assertIsInstance(storage, AnalysisRepositoryProtocol)
                self.assertIsNone(storage.get_detail("unknown"))
                storage.complete(
                    self.result(), attempt=1, source_attempts=dict.fromkeys(mock_agents(), 1)
                )
                saved = storage.get_detail("contract")
                self.assertEqual(saved.request.status, "completed")
                self.assertEqual(saved.result, self.result().model_dump(mode="json"))

    def test_historical_result_is_not_revalidated_or_rewritten(self):
        self.storage.complete(
            self.result(), attempt=1, source_attempts=dict.fromkeys(mock_agents(), 1)
        )
        historical = {"request_id": "contract", "old_field": {"value": 12}}
        with connect(self.path) as db:
            db.execute(
                "UPDATE analysis_requests SET result_json=? WHERE request_id='contract'",
                (json.dumps(historical),),
            )
        self.assertEqual(self.storage.get_detail("contract").result, historical)

    async def test_answer_claim_is_boolean_and_resume_data_is_separate(self):
        settings = ExecutionSettings(db_path=self.path)
        waiting = await execute_analysis(
            "시험 주소",
            request_id="waiting",
            settings=settings,
            allow_questions=True,
            **mock_dependencies("analysis", allow_questions=True),
        )
        submission = AnswerSubmission(
            request_id="waiting", question_set_id=waiting.question_set_id, answers=[]
        )
        self.assertIs(self.storage.claim_answers(submission), True)
        self.assertIs(self.storage.claim_answers(submission), False)
        bundle = self.storage.load_resume("waiting")
        self.assertEqual(bundle["task"].request_id, "waiting")
        self.assertEqual(len(bundle["request"].analyses), 3)

    def test_failed_completion_leaves_no_result_history(self):
        with self.assertRaises(ValueError):
            self.storage.complete(
                self.result(), attempt=1, source_attempts=dict.fromkeys(mock_agents(), 2)
            )
        self.assertEqual(self.storage.get_detail("contract").request.status, "running")
        self.assertEqual(repository.list_decision_results("contract", db_path=self.path), [])
