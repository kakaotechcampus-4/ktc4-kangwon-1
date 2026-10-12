"""운영 오류 로그가 원문·연쇄 예외를 노출하지 않는지 확인합니다."""

import logging
import unittest

from app.logging import log_exception


class SafeLoggingTests(unittest.TestCase):
    def test_exception_chain_is_replaced_but_traceback_remains(self):
        logger = logging.getLogger("safe-log-test")
        secret = "SECRET-USER-INPUT"
        with self.assertLogs(logger, level="ERROR") as captured:
            try:
                try:
                    raise ValueError(secret)
                except ValueError as cause:
                    raise RuntimeError(secret) from cause
            except RuntimeError as exc:
                log_exception(logger, "외부 실행 실패", exc)
        self.assertIn("Traceback", captured.output[0])
        self.assertIn("외부 실행 실패", captured.output[0])
        self.assertNotIn(secret, captured.output[0])
        self.assertNotIn("direct cause", captured.output[0])
