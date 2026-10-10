"""진행 화면용 비동기 실행(wait=false)과 단계 이벤트 폴링을 검사합니다."""

import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db import repository
from app.db.connection import initialize
from app.main import create_app
from app.services.settings import ExecutionSettings


class AnalysisEventTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(
            patch("httpx.AsyncClient.send", side_effect=AssertionError("외부 호출 금지"))
        )
        self.settings = ExecutionSettings(db_path=Path(folder) / "test.sqlite3")

    def client(self, settings=None):
        return self.enterContext(
            TestClient(create_app(settings=settings or self.settings, load_env=False))
        )

    def wait_finished(self, client, request_id, limit=20.0):
        after, events = 0, []
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            page = client.get(f"/api/v1/analyses/{request_id}/events?after={after}").json()
            events += page["events"]
            after = page["next_after"]
            if page["finished"]:
                return page["status"], events
            time.sleep(0.05)
        self.fail("분석이 제한시간 안에 끝나지 않았습니다.")

    def test_background_run_reports_steps_in_order(self):
        client = self.client()
        started = client.post(
            "/api/v1/analyses?mock=true&wait=false", json={"address": "시험 주소"}
        )
        self.assertEqual(started.status_code, 202)
        request_id = started.json()["request_id"]
        self.assertEqual(started.headers["X-Request-ID"], request_id)

        status, events = self.wait_finished(client, request_id)
        self.assertEqual(status, "completed")
        steps = [(e["stage"], e["event"]) for e in events]
        self.assertEqual(steps[:2], [("address", "started"), ("address", "completed")])
        for agent in ("floating_population", "business_lifecycle", "commercial_area"):
            self.assertLess(steps.index((agent, "started")), steps.index((agent, "completed")))
        decision = next(e for e in events if e["stage"] == "decision" and e["event"] == "completed")
        self.assertEqual(decision["detail"]["action"], "final")
        self.assertEqual(steps[-1], ("run", "completed"))
        self.assertEqual([e["seq"] for e in events], list(range(1, len(events) + 1)))
        # 결과는 기존 조회 API로 가져갑니다.
        self.assertEqual(client.get(f"/api/v1/analyses/{request_id}").json()["status"], "completed")

    def test_multi_agent_reports_briefs_and_consults(self):
        client = self.client(replace(self.settings, analysis_mode="multi_agent"))
        started = client.post(
            "/api/v1/analyses?mock=true&wait=false", json={"address": "시험 주소", "with_map": True}
        )
        status, events = self.wait_finished(client, started.json()["request_id"])
        self.assertEqual(status, "completed")
        stages = {e["stage"] for e in events}
        self.assertTrue({"brief.floating_population", "consult.map_analysis"} <= stages)
        actions = [
            e["detail"]["action"]
            for e in events
            if e["stage"] == "decision" and e["event"] == "completed"
        ]
        self.assertEqual(actions[0], "ask_specialists")
        self.assertEqual(actions[-1], "final")

    def test_questions_wait_then_answers_resume_in_background(self):
        client = self.client()
        started = client.post(
            "/api/v1/analyses?mock=true&wait=false",
            json={"address": "시험 주소", "allow_questions": True},
        )
        request_id = started.json()["request_id"]
        status, events = self.wait_finished(client, request_id)
        self.assertEqual(status, "waiting_for_input")
        self.assertEqual((events[-1]["stage"], events[-1]["event"]), ("questions", "waiting"))
        waiting = client.get(f"/api/v1/analyses/{request_id}").json()["questions"]

        resumed = client.post(
            f"/api/v1/analyses/{request_id}/answers?mock=true&wait=false",
            json={
                "request_id": request_id,
                "question_set_id": waiting["question_set_id"],
                "answers": [],
            },
        )
        self.assertEqual(resumed.status_code, 202)
        status, more = self.wait_finished(client, request_id)
        self.assertEqual(status, "completed")
        self.assertEqual((more[-1]["stage"], more[-1]["event"]), ("run", "completed"))

    def test_concurrency_limit_returns_429(self):
        client = self.client(replace(self.settings, max_concurrency=1))
        first = client.post("/api/v1/analyses?mock=true&wait=false", json={"address": "시험 주소"})
        second = client.post("/api/v1/analyses?mock=true&wait=false", json={"address": "시험 주소"})
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 429)
        self.wait_finished(client, first.json()["request_id"])

    def test_unknown_request_events_is_404(self):
        self.assertEqual(self.client().get("/api/v1/analyses/없음/events").status_code, 404)

    def test_startup_closes_interrupted_runs(self):
        path = initialize(self.settings.db_path)
        repository.create_request("끊긴요청", "시험 주소", db_path=path)
        repository.mark_running("끊긴요청", db_path=path)
        client = self.client()
        saved = client.get("/api/v1/analyses/끊긴요청").json()
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["error"]["code"], "INTERRUPTED")


if __name__ == "__main__":
    unittest.main()
