"""평가자 설정과 공개 계약의 불변 조건을 검증합니다."""

import os
import unittest
from unittest.mock import patch

from app import schemas
from app.services.settings import ExecutionSettings


class SettingsTests(unittest.TestCase):
    def test_defaults_and_flags(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = ExecutionSettings.from_env()
            self.assertFalse(settings.evaluators_enabled)
            self.assertFalse(settings.briefing_enabled)
            self.assertEqual(settings.overall_timeout, 600)
        with patch.dict(
            os.environ, {"EVALUATORS_ENABLED": "TRUE", "BRIEFING_ENABLED": "1"}, clear=True
        ):
            settings = ExecutionSettings.from_env()
            self.assertTrue(settings.evaluators_enabled)
            self.assertTrue(settings.briefing_enabled)
            self.assertEqual(settings.overall_timeout, 1200)

    def test_conflict_and_invalid_values(self):
        with patch.dict(
            os.environ, {"BRIEFING_ENABLED": "0", "ANALYSIS_MODE": "multi_agent"}, clear=True
        ):
            with self.assertLogs("app.services.settings", level="WARNING") as logs:
                self.assertEqual(ExecutionSettings.from_env().analysis_mode, "single_decision")
            self.assertEqual(len(logs.records), 1)
        for key in ("BRIEFING_ENABLED", "EVALUATORS_ENABLED"):
            with patch.dict(os.environ, {key: "yes"}, clear=True), self.assertRaises(ValueError):
                ExecutionSettings.from_env()

    def test_log_rules(self):
        base = {"evaluator": "founder", "index": 0, "reason": "원자료 확인"}
        for decision, applied, dropped in (
            ("accepted", "반영", None),
            ("partial", "반영", "제외"),
            ("rejected", None, "제외"),
            ("unreviewed", None, None),
        ):
            entry = schemas.EvaluationLogEntry(
                **base, decision=decision, applied=applied, dropped=dropped
            )
            self.assertEqual(entry.decision, decision)
            with self.assertRaises(ValueError):
                schemas.EvaluationLogEntry(
                    **base,
                    decision=decision,
                    applied=None if applied else "잘못된 반영",
                    dropped=dropped,
                )

    def test_evaluation_rules(self):
        base = {"request_id": "test", "evaluator": "founder"}
        schemas.Evaluation(**base, source="model", verdict="agree")
        schemas.Evaluation(**base, source="failed")
        for changes in (
            {"source": "model"},
            {"source": "failed", "verdict": "agree"},
            {"source": "model", "verdict": "agree", "comments": [{"index": 1, "comment": "확인"}]},
        ):
            with self.assertRaises(ValueError):
                schemas.Evaluation(**base, **changes)
