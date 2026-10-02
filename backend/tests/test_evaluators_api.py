"""평가 목업 생성·질문 재개와 공개 응답의 내부 기록 제외를 확인합니다."""

import json
import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.api.v1.mock import interactive_decision
from app.main import create_app
from app.services.settings import ExecutionSettings


class ApiTests(unittest.TestCase):
    def test_mock_retry_before_evaluation_never_builds_real_generators(self):
        from app.agents.decision.agent import generate_decision
        from app.agents.evaluators.agent import generate_evaluation

        with tempfile.TemporaryDirectory() as directory:
            settings = ExecutionSettings(
                db_path=Path(directory) / "retry.sqlite3", evaluators_enabled=True
            )
            with (
                TestClient(create_app(settings=settings, load_env=False)) as client,
                patch("socket.socket.connect", side_effect=AssertionError("네트워크 금지")),
            ):
                with patch(
                    "app.services.mocking.interactive_decision",
                    return_value=Mock(side_effect=RuntimeError("초안 실패")),
                ):
                    failed = client.post(
                        "/api/v1/analyses?mock=true", json={"address": "시험 주소"}
                    )
                self.assertEqual(failed.status_code, 502)
                request_id = failed.headers["X-Request-ID"]
                path = f"/api/v1/analyses/{request_id}"
                saved = client.get(path).json()
                self.assertEqual(saved["status"], "failed")
                self.assertIsNone(saved["evaluation"]["draft"])
                with (
                    patch(
                        "app.services.analysis.build_evaluator_generators",
                        side_effect=AssertionError("실제 평가자 생성 금지"),
                    ) as factory,
                    patch("app.services.analysis.partial", wraps=partial) as construct,
                ):
                    response = client.post(
                        path + "/retry-decision?mock=true",
                        json={"failed_at": saved["completed_at"]},
                    )
                self.assertEqual(response.status_code, 200, response.text)
                factory.assert_not_called()
                self.assertFalse(
                    any(
                        call.args[0] in (generate_decision, generate_evaluation)
                        for call in construct.call_args_list
                    )
                )
                completed = client.get(path).json()
                self.assertEqual(completed["status"], "completed")
                self.assertEqual(len(completed["evaluation"]["evaluations"]), 4)

    def test_mock_resume_never_builds_real_evaluator_generators(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = ExecutionSettings(
                db_path=Path(directory) / "resume.sqlite3",
                analysis_mode="multi_agent",
                evaluators_enabled=True,
            )
            with (
                TestClient(create_app(settings=settings, load_env=False)) as client,
                patch("socket.socket.connect", side_effect=AssertionError("네트워크 금지")),
            ):
                started = client.post(
                    "/api/v1/analyses?mock=true",
                    json={"address": "시험 주소", "allow_questions": True, "with_map": True},
                )
                self.assertEqual(started.status_code, 200, started.text)
                waiting = started.json()
                path = f"/api/v1/analyses/{waiting['request_id']}"
                self.assertEqual(len(client.get(path).json()["evaluation"]["evaluations"]), 4)
                with patch(
                    "app.services.analysis.build_evaluator_generators",
                    side_effect=AssertionError("실제 평가자 생성 금지"),
                ) as factory:
                    response = client.post(
                        path + "/answers?mock=true",
                        json={
                            "request_id": waiting["request_id"],
                            "question_set_id": waiting["question_set_id"],
                            "answers": [],
                        },
                    )
                self.assertEqual(response.status_code, 200, response.text)
                factory.assert_not_called()
                self.assertEqual(client.get(path).json()["status"], "completed")

    def test_mock_retry_before_and_after_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            for phase in ("draft", "final"):
                settings = ExecutionSettings(
                    db_path=Path(directory) / f"{phase}.sqlite3", evaluators_enabled=True
                )
                with (
                    TestClient(create_app(settings=settings, load_env=False)) as client,
                    patch("socket.socket.connect", side_effect=AssertionError("네트워크 금지")),
                ):

                    def broken(prompt, payload, phase=phase):
                        if phase == "draft" or "evaluation" in json.loads(payload):
                            raise RuntimeError("모델 실패")
                        return interactive_decision(with_map=False, allow_questions=False)(
                            prompt, payload
                        )

                    with patch("app.services.mocking.interactive_decision", return_value=broken):
                        failed = client.post(
                            "/api/v1/analyses?mock=true", json={"address": "시험 주소"}
                        )
                    self.assertEqual(failed.status_code, 502)
                    request_id = failed.headers["X-Request-ID"]
                    saved = client.get(f"/api/v1/analyses/{request_id}").json()
                    result = client.post(
                        f"/api/v1/analyses/{request_id}/retry-decision?mock=true",
                        json={"failed_at": saved["completed_at"]},
                    )
                    self.assertEqual(result.status_code, 200, result.text)
                    saved = client.get(f"/api/v1/analyses/{request_id}").json()
                    self.assertEqual(saved["evaluation"]["log"][0]["decision"], "partial")

    def test_mock_create_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            for mode in ("single_decision", "multi_agent"):
                settings = ExecutionSettings(
                    db_path=Path(directory) / (mode + ".sqlite3"),
                    analysis_mode=mode,
                    evaluators_enabled=True,
                )
                with (
                    TestClient(create_app(settings=settings, load_env=False)) as client,
                    patch("socket.socket.connect", side_effect=AssertionError("네트워크 금지")),
                ):
                    response = client.post(
                        "/api/v1/analyses?mock=true",
                        json={"address": "시험 주소", "allow_questions": True},
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    waiting = response.json()
                    request_id = waiting["request_id"]
                    response = client.post(
                        f"/api/v1/analyses/{request_id}/answers?mock=true",
                        json={
                            "request_id": request_id,
                            "question_set_id": waiting["question_set_id"],
                            "answers": [],
                        },
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    evaluation = client.get(f"/api/v1/analyses/{request_id}").json()["evaluation"]
                    self.assertEqual(
                        [e["evaluator"] for e in evaluation["evaluations"]],
                        ["examiner", "founder", "customer", "landlord_advocate"],
                    )
                    self.assertEqual(evaluation["log"][0]["decision"], "partial")
                    self.assertNotIn("notes", str(evaluation))
                    events = client.get(f"/api/v1/analyses/{request_id}/events").json()["events"]
                    stages = [(e["stage"], e["event"], e["detail"].get("phase")) for e in events]
                    self.assertIn(("decision", "started", "draft"), stages)
                    self.assertIn(("decision", "started", "final"), stages)
                    evaluation_starts = [
                        i
                        for i, (stage, event, _) in enumerate(stages)
                        if stage.startswith("evaluate.") and event == "started"
                    ]
                    self.assertEqual(len(evaluation_starts), 4)
                    self.assertLess(
                        stages.index(("decision", "completed", "draft")), min(evaluation_starts)
                    )
                    self.assertLess(
                        max(evaluation_starts), stages.index(("decision", "started", "final"))
                    )

    def test_mock_without_questions_still_logs_and_off_omits_key(self):
        with tempfile.TemporaryDirectory() as directory:
            for enabled in (False, True):
                settings = ExecutionSettings(
                    db_path=Path(directory) / f"{enabled}.sqlite3", evaluators_enabled=enabled
                )
                with (
                    TestClient(create_app(settings=settings, load_env=False)) as client,
                    patch("socket.socket.connect", side_effect=AssertionError("네트워크 금지")),
                ):
                    response = client.post(
                        "/api/v1/analyses?mock=true", json={"address": "시험 주소"}
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    saved = client.get(f"/api/v1/analyses/{response.json()['request_id']}").json()
                    self.assertEqual("evaluation" in saved, enabled)
                    if enabled:
                        self.assertEqual(saved["evaluation"]["log"][0]["decision"], "partial")
