"""닫힌 요청이 뒤늦은 결과로 되살아나지 않는지 검증합니다."""

import tempfile
import unittest
from pathlib import Path

from app.infrastructure.persistence.repository import requests as repo
from app.infrastructure.persistence.connection import initialize

# 스키마가 result_json 안의 request_id와 행의 request_id가 같은지 검사합니다.
RESULT = '{"request_id": "request", "run": "first"}'
OTHER_RESULT = '{"request_id": "request", "run": "second"}'


class ClosedRequestGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "requests.sqlite3"
        initialize(self.path)
        repo.create_request("request", "주소", db_path=self.path)

    def status(self):
        return repo.get_request("request", db_path=self.path)["status"]

    def test_running_request_is_closed_with_the_result(self):
        repo.mark_running("request", db_path=self.path)

        saved = repo.save_outcome(
            "request",
            result_text=RESULT,
            completed_at="2026-01-01T00:00:00+00:00",
            db_path=self.path,
        )

        self.assertEqual(saved, 1)
        self.assertEqual(self.status(), "completed")

    def test_answered_request_can_still_be_completed(self):
        # 질문 대기에서 답을 받아 이어 간 뒤 끝나는 정상 흐름입니다.
        repo.mark_running("request", db_path=self.path)
        repo.save_outcome("request", db_path=self.path)
        self.assertEqual(self.status(), "waiting_for_input")

        saved = repo.save_outcome(
            "request",
            result_text=RESULT,
            completed_at="2026-01-01T00:00:00+00:00",
            db_path=self.path,
        )

        self.assertEqual(saved, 1)
        self.assertEqual(self.status(), "completed")

    def test_failed_request_is_not_reopened_by_a_late_result(self):
        # 서버가 다시 켜지며 진행 중이던 요청을 실패로 닫은 뒤,
        # 뒤늦게 끝난 작업이 결과를 저장하려는 상황입니다.
        repo.mark_running("request", db_path=self.path)
        self.assertEqual(repo.fail_interrupted(db_path=self.path), 1)
        self.assertEqual(self.status(), "failed")

        saved = repo.save_outcome(
            "request",
            result_text=RESULT,
            completed_at="2026-01-01T00:00:00+00:00",
            db_path=self.path,
        )

        self.assertEqual(saved, 0)
        self.assertEqual(self.status(), "failed")
        self.assertIsNone(repo.get_request("request", db_path=self.path)["result_json"])

    def test_failed_request_is_not_put_back_into_waiting(self):
        repo.mark_running("request", db_path=self.path)
        repo.fail_interrupted(db_path=self.path)

        self.assertEqual(repo.save_outcome("request", db_path=self.path), 0)
        self.assertEqual(self.status(), "failed")

    def test_completed_request_is_not_overwritten(self):
        repo.mark_running("request", db_path=self.path)
        repo.save_outcome(
            "request",
            result_text=RESULT,
            completed_at="2026-01-01T00:00:00+00:00",
            db_path=self.path,
        )

        saved = repo.save_outcome(
            "request",
            result_text=OTHER_RESULT,
            completed_at="2026-01-02T00:00:00+00:00",
            db_path=self.path,
        )

        self.assertEqual(saved, 0)
        self.assertEqual(repo.get_request("request", db_path=self.path)["result_json"], RESULT)


if __name__ == "__main__":
    unittest.main()
