"""예외의 원래 종류를 유지하면서 교정 진단을 보존합니다."""

import asyncio
import unittest
from unittest.mock import Mock

from app.agents.decision.agent import evaluate
from app.execution.errors import (
    DecisionExecutionError,
    capture_decision_failures,
    failure_diagnostics,
)
from app.mocks import mock_agents, mock_generate, mock_site
from app.schemas import AnalysisTask, DecisionRequest


class ExecutionDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        task = AnalysisTask(request_id="diagnostics", site=mock_site())
        self.request = DecisionRequest(
            request_id=task.request_id,
            address=task.site.input_address,
            analyses=[await fn(task) for fn in mock_agents().values()],
        )
        self.broken = mock_generate("", "")
        self.broken["recommendations"][0]["evidence"][0]["path"] = "/missing"

    async def test_execution_error_declares_original_error_and_failures(self):
        original = RuntimeError("정제하지 않은 모델 응답")
        with self.assertRaises(DecisionExecutionError) as caught:
            await evaluate(self.request, generate=Mock(side_effect=[self.broken, original]))
        self.assertIs(caught.exception.error, original)
        self.assertEqual(caught.exception.failures[0]["invalid_path"], "/missing")
        self.assertNotIn(str(original), str(caught.exception))

    async def test_public_service_boundary_can_rethrow_original_error(self):
        original = ValueError("정제하지 않은 모델 응답")

        @capture_decision_failures
        async def run():
            try:
                return await evaluate(
                    self.request, generate=Mock(side_effect=[self.broken, original])
                )
            except DecisionExecutionError as error:
                self.assertEqual(failure_diagnostics(error)[0]["invalid_path"], "/missing")
                raise

        with self.assertRaises(ValueError) as caught:
            await run()
        self.assertIs(caught.exception, original)
        self.assertFalse(hasattr(original, "failures"))

    async def test_cancellation_is_not_wrapped_and_keeps_scoped_diagnostics(self):
        cancellation = asyncio.CancelledError()

        @capture_decision_failures
        async def run():
            try:
                await evaluate(self.request, generate=Mock(side_effect=[self.broken, cancellation]))
            except asyncio.CancelledError as error:
                self.assertIs(error, cancellation)
                self.assertEqual(failure_diagnostics(error)[0]["invalid_path"], "/missing")
                self.assertFalse(hasattr(error, "failures"))
                raise

        with self.assertRaises(asyncio.CancelledError):
            await run()

    async def test_no_diagnostics_leak_into_next_execution(self):
        @capture_decision_failures
        async def run():
            try:
                await evaluate(
                    self.request,
                    generate=Mock(side_effect=[self.broken, asyncio.CancelledError()]),
                )
            except asyncio.CancelledError:
                pass

        await run()
        self.assertIsNone(failure_diagnostics(RuntimeError("next request")))
