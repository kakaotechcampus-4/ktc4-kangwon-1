"""저장된 재개 상태가 실행 가능한 계약인지 검사합니다."""

import copy
import unittest

from app.agents.orchestration.state import normalize_resume_state, validate_resume_state
from app.execution.validation import validate_execution_state
from app.mocks import mock_agents, mock_site
from app.schemas import AnalysisTask


class ResumeValidationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.task = AnalysisTask(request_id="resume", site=mock_site())
        self.state = {
            "task": self.task,
            "analyses": [await fn(self.task) for fn in mock_agents().values()],
            "consult_round": 0,
        }

    def test_legacy_state_is_normalized_before_validation(self):
        original = {**self.state, "context": {"feedback": ["저장 근거"]}}
        before = copy.deepcopy(original)
        restored = normalize_resume_state(original, mode="multi_agent")
        validate_resume_state(restored, mode="multi_agent", retry_only=False)
        self.assertEqual(original, before)

    def test_invalid_map_and_round_are_rejected(self):
        for fields in (
            {"map_observation": "invalid"},
            {"consult_round": -1},
            {"consult_round": True},
            {"consult_round": 7},
        ):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                validate_resume_state(
                    {**self.state, **fields}, mode="multi_agent", retry_only=False
                )

    def test_source_request_id_mismatch_is_rejected(self):
        sources = [*self.state["analyses"]]
        sources[0] = sources[0].model_copy(update={"request_id": "other"})
        with self.assertRaises(ValueError):
            validate_resume_state(
                {**self.state, "analyses": sources}, mode="multi_agent", retry_only=False
            )

    def test_evaluations_require_draft(self):
        with self.assertRaises(ValueError):
            validate_resume_state(
                {**self.state, "evaluations": []}, mode="multi_agent", retry_only=True
            )


class ExecutionStateValidationTests(unittest.TestCase):
    def test_corrupt_call_history_is_rejected_before_execution(self):
        for calls in (
            ["corrupt"],
            [{}],
            [{"attempt": "1"}],
            [{"attempt": True}],
            [{"attempt": 0}],
            [{"attempt": 2}],
            [{"attempt": 1}, {"attempt": 1}],
        ):
            with (
                self.subTest(calls=calls),
                self.assertRaisesRegex(ValueError, "모델 호출 예산이 올바르지 않습니다."),
            ):
                validate_execution_state({"budget": {"used": 1, "calls": calls}})

    def test_legacy_counter_and_valid_started_call_remain_usable(self):
        validate_execution_state({"budget": {"used": 1, "calls": []}})
        validate_execution_state({"budget": {"used": 1, "calls": [{"attempt": 1}]}})

    def test_empty_legacy_execution_state_remains_valid(self):
        validate_execution_state({})

    def test_corrupt_execution_values_are_rejected(self):
        for state in (
            {"budget": {"used": -1, "calls": []}},
            {"budget": {"used": 1, "calls": "invalid"}},
            {"elapsed_seconds": float("nan")},
            {"elapsed_seconds": -1},
            {"time_limit": 0},
            {"capabilities": {"evaluators": "false"}},
        ):
            with self.subTest(state=state), self.assertRaises(ValueError):
                validate_execution_state(state)
