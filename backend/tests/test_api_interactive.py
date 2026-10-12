"""질문·지도 선택 조회의 HTTP 계약을 실제 저장 흐름으로 검사합니다."""

import asyncio
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.settings import ExecutionSettings


class InteractiveApiTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(
            patch("httpx.AsyncClient.send", side_effect=AssertionError("외부 호출 금지"))
        )
        self.client = self.enterContext(
            TestClient(
                create_app(
                    settings=ExecutionSettings(db_path=Path(folder) / "test.sqlite3"),
                    load_env=False,
                )
            )
        )

    def start(self, **options):
        return self.client.post(
            "/api/v1/analyses?mock=true", json={"address": "시험 주소", **options}
        )

    def test_radius_is_validated_and_persisted(self):
        result = self.start(radius_m=300)
        self.assertEqual(result.status_code, 200)
        saved = self.client.get("/api/v1/analyses/" + result.json()["request_id"]).json()
        self.assertEqual(saved["radius_m"], 300)
        for radius in (0, -1, True, "300", 1.5):
            self.assertEqual(self.start(radius_m=radius).status_code, 422)

    def test_concurrent_different_answers_return_conflict_not_server_error(self):
        from app.api.v1.routes import resume_runner
        from app.services.analysis import resume_analysis

        waiting = self.start(allow_questions=True).json()
        started, release = threading.Event(), threading.Event()

        async def synchronized(submission, **kwargs):
            started.set()
            await asyncio.to_thread(release.wait, 5)
            return await resume_analysis(submission, **kwargs)

        self.client.app.dependency_overrides[resume_runner] = lambda: synchronized

        def submit(value):
            return self.client.post(
                f"/api/v1/analyses/{waiting['request_id']}/answers?mock=true",
                json={
                    "request_id": waiting["request_id"],
                    "question_set_id": waiting["question_set_id"],
                    "answers": [{"field": "floor", "status": "answered", "value": value}],
                },
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(submit, "1층")
            try:
                self.assertTrue(started.wait(5))
                second = pool.submit(submit, "2층")
                second_result = second.result(timeout=5)
            finally:
                release.set()
            results = [first.result(timeout=5), second_result]
        self.assertEqual(sorted(results), [200, 409])

    def test_map_questions_answers_and_duplicate_submission(self):
        response = self.start(radius_m=300, allow_questions=True, with_map=True)
        self.assertEqual(response.status_code, 200)
        waiting = response.json()
        self.assertEqual(waiting["status"], "waiting_for_input")
        path = "/api/v1/analyses/" + waiting["request_id"]
        saved = self.client.get(path).json()
        self.assertEqual(saved["questions"], waiting)
        self.assertEqual(len(saved["analyses"]), 3)
        self.assertEqual(saved["map_observation"]["radius_m"], 300)
        self.assertNotIn("snapshot_json", saved)
        answer = {
            "request_id": waiting["request_id"],
            "question_set_id": waiting["question_set_id"],
            "answers": [{"field": "floor", "status": "answered", "value": "1층"}],
        }
        final = self.client.post(path + "/answers?mock=true", json=answer)
        self.assertEqual(final.status_code, 200, final.text)
        self.assertIsNotNone(final.json()["map_observation"])
        again = self.client.post(path + "/answers?mock=true", json=answer)
        self.assertEqual(again.json(), final.json())
        answer["answers"][0]["value"] = "3층"
        self.assertEqual(
            self.client.post(path + "/answers?mock=true", json=answer).status_code, 409
        )
        self.assertEqual(self.client.get(path).json()["status"], "completed")

    def test_wrong_question_and_skip(self):
        waiting = self.start(allow_questions=True).json()
        self.assertEqual(waiting["status"], "waiting_for_input")
        path = "/api/v1/analyses/" + waiting["request_id"] + "/answers?mock=true"
        answer = {"request_id": waiting["request_id"], "question_set_id": "wrong", "answers": []}
        self.assertEqual(self.client.post(path, json=answer).status_code, 409)
        answer["question_set_id"] = waiting["question_set_id"]
        self.assertEqual(self.client.post(path, json=answer).status_code, 200)
        answer["request_id"] = "wrong"
        self.assertEqual(self.client.post(path, json=answer).status_code, 422)
        self.assertEqual(
            self.client.post(
                "/api/v1/analyses/missing/answers?mock=true",
                json={**answer, "request_id": "missing"},
            ).status_code,
            404,
        )

    def test_map_does_not_enable_questions_and_options_are_strict(self):
        result = self.start(with_map=True)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["agent_id"], "decision")
        self.assertEqual(result.json()["map_observation"]["status"], "no_data")
        for options in ({"with_map": "true"}, {"allow_questions": 1}, {"unknown": True}):
            self.assertEqual(self.start(**options).status_code, 422)

    def test_real_path_registers_optional_tools(self):
        from app.api.v1.mock import interactive_decision, map_observation
        from app.api.v1.routes import analysis_runner
        from app.mocks import mock_agents, mock_resolve
        from app.services.analysis import execute_analysis

        async def run(address, **kwargs):
            self.assertEqual(kwargs["radius_m"], 650)
            self.assertTrue(kwargs["supplements"])
            self.assertIs(kwargs["map_lookup"], map_observation)
            return await execute_analysis(
                address,
                **{
                    **kwargs,
                    "resolve": mock_resolve,
                    "agents": mock_agents(),
                    "generate": interactive_decision(with_map=True, allow_questions=False),
                    "supplements": [],
                },
            )

        self.client.app.dependency_overrides[analysis_runner] = lambda: run
        with patch("app.agents.map_analysis.agent.observe", map_observation):
            result = self.client.post(
                "/api/v1/analyses", json={"address": "시험 주소", "radius_m": 650, "with_map": True}
            )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["map_observation"]["radius_m"], 650)
