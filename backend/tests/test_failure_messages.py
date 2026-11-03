"""분석이 실패하면 원인에 맞는 안내와 다음에 할 일을 사용자에게 보여 줍니다."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from app.address import GeocodeError
from app.db.connection import connect, initialize
from app.db.repository import create_request, fail_interrupted, mark_running
from app.services.analysis import public_failure

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
