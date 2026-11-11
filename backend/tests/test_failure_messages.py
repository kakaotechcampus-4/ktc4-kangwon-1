import asyncio
import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from app.application.analysis import public_failure
from app.application.errors import AddressError
from app.infrastructure.clients.address import GeocodeError
from app.infrastructure.persistence.connection import connect, initialize
from app.infrastructure.persistence.repository import create_request, fail_interrupted, mark_running
from app.infrastructure.persistence.repository.requests import STALE_AFTER_SECONDS

INTERRUPTED = "서비스 점검으로 분석이 멈췄어요. 다시 분석해 주세요."


class PublicFailureTests(unittest.TestCase):
    def check(self, exc, stage, code, message):
        error = public_failure(exc, stage)
        self.assertEqual((error.code, error.message), (code, message))

    def test_cancel_in_loop_is_interrupted(self):
        self.check(asyncio.CancelledError(), "루프", "INTERRUPTED", INTERRUPTED)

    def test_cancel_while_collecting_is_interrupted(self):
        self.check(asyncio.CancelledError(), "조회·채점", "INTERRUPTED", INTERRUPTED)

    def test_address_failure(self):
        self.check(
            GeocodeError("NOT_FOUND", "주소를 찾지 못했습니다."),
            "수집",
            "ADDRESS_FAILED",
            "주소를 확인하지 못했어요. 주소를 다시 확인한 뒤 분석해 주세요.",
        )

    def test_outside_seoul_keeps_its_notice(self):
        self.check(
            AddressError("OUTSIDE_SEOUL", "x"),
            "수집",
            "OUTSIDE_SEOUL",
            "지금은 서울 상가만 분석할 수 있어요.",
        )

    def test_address_service_outage_is_not_an_address_problem(self):
        for code in ("UPSTREAM_TIMEOUT", "UPSTREAM_FAILED", "KAKAO_AUTH", "BAD_RESPONSE"):
            self.check(
                GeocodeError(code, "x"),
                "수집",
                "AGENTIC_FAILED",
                "분석을 끝까지 마치지 못했어요. 잠시 후 다시 분석해 주세요.",
            )

    def test_any_loop_failure_is_ai(self):
        for exc in (RuntimeError("LLM_INVALID_JSON"), TimeoutError()):
            self.check(
                exc,
                "루프",
                "AI_FAILED",
                "AI 분석이 끝나지 못했어요. 잠시 후 다시 분석해 주세요.",
            )

    def test_data_timeout(self):
        self.check(
            TimeoutError(),
            "조회·채점",
            "DATA_TIMEOUT",
            "주변 자료를 불러오는 데 시간이 너무 오래 걸렸어요. 잠시 후 다시 분석해 주세요.",
        )

    def test_data_failure(self):
        for stage in ("조회·채점", "채점"):
            self.check(
                OSError("disk"),
                stage,
                "DATA_FAILED",
                "주변 자료를 불러오지 못했어요. 잠시 후 다시 분석해 주세요.",
            )

    def test_other_failure(self):
        self.check(
            OSError("disk"),
            "수집",
            "AGENTIC_FAILED",
            "분석을 끝까지 마치지 못했어요. 잠시 후 다시 분석해 주세요.",
        )


class InterruptedTests(unittest.TestCase):
    def test_fail_interrupted_uses_same_notice(self):
        with tempfile.TemporaryDirectory() as temp:
            path = initialize(Path(temp) / "interrupted.sqlite3")
            create_request("r1", "서울 송파구 위례광장로 199", db_path=path)
            mark_running("r1", db_path=path)
            self.assertEqual(fail_interrupted(db_path=path), 1)
            with connect(path) as db:
                (error,) = db.execute(
                    "SELECT error_json FROM analysis_requests WHERE request_id='r1'"
                ).fetchone()
            body = json.loads(error)
            self.assertEqual((body["code"], body["message"]), ("INTERRUPTED", INTERRUPTED))


class OtherServerTests(unittest.TestCase):
    def test_request_running_on_another_server_is_left_alone(self):
        with tempfile.TemporaryDirectory() as temp:
            path = initialize(Path(temp) / "two-servers.sqlite3")
            with patch.dict(os.environ, {"CHAEUM_INSTANCE": "8001"}):
                create_request("old", "서울 송파구 위례광장로 199", db_path=path)
                mark_running("old", db_path=path)
            with patch.dict(os.environ, {"CHAEUM_INSTANCE": "8002"}):
                create_request("mine", "서울 송파구 위례광장로 199", db_path=path)
                mark_running("mine", db_path=path)
                self.assertEqual(fail_interrupted(db_path=path), 1)
            self.assertEqual(_statuses(path), {"old": "running", "mine": "failed"})

    def test_same_server_restart_closes_its_own_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            path = initialize(Path(temp) / "restart.sqlite3")
            with patch.dict(os.environ, {"CHAEUM_INSTANCE": "8001"}):
                create_request("pending", "서울 송파구 위례광장로 199", db_path=path)
                create_request("running", "서울 송파구 위례광장로 199", db_path=path)
                mark_running("running", db_path=path)
                self.assertEqual(fail_interrupted(db_path=path), 2)
            self.assertEqual(_statuses(path), {"pending": "failed", "running": "failed"})

    def test_request_too_old_to_be_running_anywhere_is_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = initialize(Path(temp) / "stale.sqlite3")
            with patch.dict(os.environ, {"CHAEUM_INSTANCE": "8001"}):
                create_request("fresh", "서울 송파구 위례광장로 199", db_path=path)
                create_request("stale", "서울 송파구 위례광장로 199", db_path=path)
                mark_running("stale", db_path=path)
            old = (datetime.now(UTC) - timedelta(seconds=STALE_AFTER_SECONDS + 60)).isoformat()
            with connect(path) as db:
                db.execute(
                    "UPDATE analysis_requests SET created_at=? WHERE request_id='stale'", (old,)
                )
            with patch.dict(os.environ, {"CHAEUM_INSTANCE": "8002"}):
                self.assertEqual(fail_interrupted(db_path=path), 1)
            self.assertEqual(_statuses(path), {"fresh": "pending", "stale": "failed"})

    def test_request_without_owner_record_follows_age_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = initialize(Path(temp) / "legacy.sqlite3")
            create_request("legacy", "서울 송파구 위례광장로 199", db_path=path)
            mark_running("legacy", db_path=path)
            with connect(path) as db:
                db.execute("DELETE FROM analysis_workers")
            self.assertEqual(fail_interrupted(db_path=path), 0)
            self.assertEqual(_statuses(path), {"legacy": "running"})


def _statuses(path):
    with connect(path) as db:
        return dict(db.execute("SELECT request_id,status FROM analysis_requests").fetchall())
