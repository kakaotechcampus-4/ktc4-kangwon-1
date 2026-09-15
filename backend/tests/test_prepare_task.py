"""주소 준비의 입력 검증을 검사합니다."""

import io
import json
import os
import runpy
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID

from pydantic import ValidationError

from app import orchestrator
from app.agents.orchestration import tools, workflow
from app.schemas import AnalysisTask, Site


def sample_site():
    """실제 위치가 아닌 검증용 좌표입니다."""
    return Site(input_address="주소", road_address="도로명주소",
                detail_address="원일빌딩 1층", latitude=0.0, longitude=0.0)


class PrepareTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_import_uses_same_workflow(self):
        self.assertIs(orchestrator.prepare_task, workflow.prepare_task)
        self.assertIs(orchestrator.run_analysis, workflow.run_analysis)

    async def test_prepares_task(self):
        self.assertTrue(callable(getattr(orchestrator, "prepare_task", None)))
        resolve = AsyncMock(return_value=sample_site())
        task = await orchestrator.prepare_task(
            "  주소  ", resolve=resolve, request_id="request-1")
        resolve.assert_awaited_once_with("주소")
        self.assertEqual(task.request_id, "request-1")
        self.assertEqual(task.site.detail_address, "원일빌딩 1층")

    async def test_generates_distinct_ids(self):
        resolve = AsyncMock(return_value=sample_site())
        first = await orchestrator.prepare_task("주소", resolve=resolve)
        second = await orchestrator.prepare_task("주소", resolve=resolve)
        self.assertEqual(UUID(first.request_id).version, 4)
        self.assertNotEqual(first.request_id, second.request_id)

    async def test_rejects_blank_address_before_lookup(self):
        resolve = AsyncMock(return_value=sample_site())
        with self.assertRaises(ValueError):
            await orchestrator.prepare_task(" \t ", resolve=resolve)
        resolve.assert_not_awaited()

    async def test_rejects_invalid_explicit_id(self):
        with self.assertRaises(ValidationError):
            await orchestrator.prepare_task(
                "주소", resolve=AsyncMock(return_value=sample_site()), request_id="")

    async def test_revalidates_resolver_output(self):
        for update in ({"latitude": 91.0}, {"road_address": None, "jibun_address": None}):
            with self.subTest(update=update):
                invalid = sample_site().model_copy(update=update)
                with self.assertRaises(ValidationError):
                    await orchestrator.prepare_task(
                        "주소", resolve=AsyncMock(return_value=invalid))

    async def test_lookup_failure_stops_analysis(self):
        with (
            patch.object(tools, "resolve_site", side_effect=ValueError("변환 실패")),
            patch.object(workflow, "run_agents") as agents,
        ):
            with self.assertRaises(ValueError):
                await orchestrator.run_analysis("주소")
            agents.assert_not_awaited()


class PrepareTaskExampleTests(unittest.TestCase):
    def test_example_without_network_or_keys(self):
        script = Path(__file__).resolve().parents[1] / "examples" / "prepare_task.py"
        for extra, expected_code in (([], 0), (["--address", "다른 주소"], 1)):
            with self.subTest(extra=extra):
                stdout, stderr = io.StringIO(), io.StringIO()
                with (
                    patch.dict(os.environ, {}, clear=True),
                    patch("sys.argv", [str(script), "--mock", *extra]),
                    patch("httpx.AsyncClient.send", side_effect=AssertionError("외부 연결 금지")),
                    patch("httpx.Client.send", side_effect=AssertionError("외부 연결 금지")),
                    redirect_stdout(stdout),
                    redirect_stderr(stderr),
                    self.assertRaises(SystemExit) as result,
                ):
                    runpy.run_path(str(script), run_name="__main__")
                self.assertEqual(result.exception.code, expected_code)
                self.assertIn("가상", stderr.getvalue())
                if expected_code == 0:
                    task = AnalysisTask.model_validate(json.loads(stdout.getvalue()))
                    self.assertIn("개롱역점", task.site.input_address)
                else:
                    self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
