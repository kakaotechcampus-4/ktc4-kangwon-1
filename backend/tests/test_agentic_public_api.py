"""단일 공개 API와 요청 DB 버전 경계를 검증합니다."""

import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.address import GeocodeError
from app.api.v1.analyses import analysis_runner
from app.db import repository
from app.db.connection import initialize
from app.main import create_app
from app.schemas import DecisionResult
from app.services.settings import ExecutionSettings


class PublicApiTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(
            patch(
                "httpx.AsyncHTTPTransport.handle_async_request",
                side_effect=AssertionError("외부 연결 금지"),
            )
        )

    def test_old_database_is_rejected_without_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.sqlite3"
            with closing(sqlite3.connect(path)) as db:
                db.execute("CREATE TABLE old_rows(value TEXT)")
                db.commit()
            with self.assertRaisesRegex(RuntimeError, "초기화"):
                initialize(path)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(
                    db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),
                    [("old_rows",)],
                )

    def test_accepted_request_is_visible_before_background_runs(self):
        async def blocked(*args, **kwargs):
            await asyncio.Event().wait()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "accepted.sqlite3"
            app = create_app(settings=ExecutionSettings(db_path=path), load_env=False)
            app.dependency_overrides[analysis_runner] = lambda: blocked
            with TestClient(app) as client:
                app.state.job_registry.max_concurrency = 1
                accepted = client.post("/api/v1/analyses?wait=false", json={"address": "시험"})
                self.assertEqual(accepted.status_code, 202)
                request_id = accepted.json()["request_id"]
                detail = client.get(f"/api/v1/analyses/{request_id}")
                self.assertEqual(detail.status_code, 200, detail.text)
                self.assertEqual(detail.json()["status"], "pending")
                self.assertIsNone(detail.json()["site"])
                self.assertIsNone(detail.json()["result"])
                self.assertEqual(client.get("/api/v1/analyses/missing").status_code, 404)
                rejected = client.post("/api/v1/analyses?wait=false", json={"address": "초과"})
                self.assertEqual(rejected.status_code, 429)
                with closing(sqlite3.connect(path)) as db:
                    self.assertEqual(
                        db.execute("SELECT count(*) FROM analysis_requests").fetchone()[0], 1
                    )

    def test_public_mock_question_resume_final_events(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = ExecutionSettings(db_path=Path(directory) / "new.sqlite3")
            with TestClient(create_app(settings=settings, load_env=False)) as client:
                response = client.post(
                    "/api/v1/analyses?mock=true", json={"address": "시험", "allow_questions": True}
                )
                self.assertEqual(response.status_code, 200, response.text)
                waiting = response.json()
                self.assertEqual(waiting["status"], "waiting_for_input")
                request_id = waiting["request_id"]
                response = client.post(
                    f"/api/v1/analyses/{request_id}/answers?mock=true",
                    json={
                        "question_session_id": waiting["question_session_id"],
                        "answers": {q["field"]: "시험 답변" for q in waiting["questions"]},
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                result = DecisionResult.model_validate(response.json())
                self.assertEqual(result.review_completeness, 1)
                raw = result.model_dump(mode="json")
                self.assertEqual(raw["condition_excluded"], [])
                legacy = {k: v for k, v in raw.items() if k != "condition_excluded"}
                self.assertEqual(DecisionResult.model_validate(legacy).condition_excluded, [])
                for update in (
                    {"evaluator_reviews": raw["evaluator_reviews"][:3]},
                    {"evaluator_reviews": [raw["evaluator_reviews"][0]] * 4},
                    {"review_completeness": 0},
                    {"top5": [raw["top5"][0]] * 2},
                    {"top5": [{**raw["top5"][0], "G": "금지"}]},
                ):
                    with self.subTest(update=update), self.assertRaises(ValidationError):
                        DecisionResult.model_validate({**raw, **update})
                detail = client.get(f"/api/v1/analyses/{request_id}").json()
                self.assertEqual(detail["status"], "completed")
                self.assertIn("rendered", detail)
                events = client.get(f"/api/v1/analyses/{request_id}/events").json()
                self.assertIn("evaluation", {e["stage"] for e in events["events"]})
                duplicate = client.post(
                    f"/api/v1/analyses/{request_id}/answers?mock=true",
                    json={
                        "question_session_id": waiting["question_session_id"],
                        "answers": {q["field"]: "시험 답변" for q in waiting["questions"]},
                    },
                )
                self.assertEqual(duplicate.status_code, 409)

    def test_input_and_answer_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = ExecutionSettings(db_path=Path(directory) / "input.sqlite3")
            with TestClient(create_app(settings=settings, load_env=False)) as client:
                self.assertEqual(client.get("/api/v1/health").json(), {"status": "ok"})
                for body, expected in (
                    ({"address": " "}, 400),
                    ({"address": ""}, 422),
                    ({"address": "시험", "radius_m": 0}, 422),
                    ({"address": "시험", "allow_questions": "true"}, 422),
                ):
                    with self.subTest(body=body):
                        self.assertEqual(
                            client.post("/api/v1/analyses?mock=true", json=body).status_code,
                            expected,
                        )
                waiting = client.post(
                    "/api/v1/analyses?mock=true", json={"address": "시험", "allow_questions": True}
                ).json()
                url = f"/api/v1/analyses/{waiting['request_id']}/answers?mock=true"
                answers = {q["field"]: "시험" for q in waiting["questions"]}
                for session, submitted, expected in (
                    ("wrong", answers, 409),
                    (waiting["question_session_id"], {}, 422),
                    (waiting["question_session_id"], {key: "가" * 501 for key in answers}, 422),
                ):
                    with self.subTest(session=session, answers=submitted):
                        response = client.post(
                            url, json={"question_session_id": session, "answers": submitted}
                        )
                        self.assertEqual(response.status_code, expected)

    def test_provider_errors_are_safe_and_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            for error, expected in (
                (GeocodeError("NOT_FOUND", "SECRET"), 400),
                (GeocodeError("UPSTREAM_TIMEOUT", "SECRET"), 502),
                (RuntimeError("SECRET"), 502),
                (ValueError("SECRET"), 500),
            ):
                app = create_app(
                    settings=ExecutionSettings(db_path=Path(directory) / "errors.sqlite3"),
                    load_env=False,
                )

                async def fail(*args, error=error, **kwargs):
                    raise error

                app.dependency_overrides[analysis_runner] = lambda: fail
                with self.subTest(error=error), TestClient(app) as client:
                    response = client.post("/api/v1/analyses?mock=true", json={"address": "시험"})
                    self.assertEqual(response.status_code, expected, response.text)
                    self.assertNotIn("SECRET", response.text)
                    self.assertIn("x-request-id", response.headers)

    def test_facts_return_whole_snapshot_beyond_citations(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "facts.sqlite3"
            app = create_app(settings=ExecutionSettings(db_path=path), load_env=False)
            with TestClient(app) as client:
                repository.create_request("before", "시험", db_path=path)
                empty = client.get("/api/v1/analyses/before/facts")
                self.assertEqual(empty.status_code, 200, empty.text)
                self.assertEqual(empty.json()["facts"], [])
                self.assertIsNone(empty.json()["snapshot_id"])
                self.assertEqual(client.get("/api/v1/analyses/missing/facts").status_code, 404)

                result = client.post("/api/v1/analyses?mock=true", json={"address": "시험"})
                self.assertEqual(result.status_code, 200, result.text)
                result = DecisionResult.model_validate(result.json())
                response = client.get(f"/api/v1/analyses/{result.request_id}/facts")
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual(body["snapshot_id"], result.snapshot_id)
                ids = {f["fact_id"] for f in body["facts"]}
                self.assertEqual(len(ids), len(body["facts"]))
                cited = {f.fact_id for f in result.facts}
                self.assertLessEqual(cited, ids)
                self.assertGreater(len(ids), len(cited))
                with closing(sqlite3.connect(path)) as db:
                    stored = db.execute(
                        "SELECT count(*) FROM facts WHERE request_id=? AND metric!='space_fit'",
                        (result.request_id,),
                    ).fetchone()[0]
                self.assertEqual(sum(f["metric"] != "space_fit" for f in body["facts"]), stored)
                self.assertNotIn("n.a.", {f["status"] for f in body["facts"]})

    def test_events_preserve_status_order_and_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite3"
            app = create_app(settings=ExecutionSettings(db_path=path), load_env=False)
            with TestClient(app) as client:
                repository.create_request("events", "시험", db_path=path)
                url = "/api/v1/analyses/events/events"
                pending = client.get(url).json()
                self.assertEqual(
                    (pending["status"], pending["finished"], pending["next_after"]),
                    ("pending", False, 0),
                )
                repository.mark_running("events", db_path=path)
                repository.append_event("events", "decision", "started", {}, db_path=path)
                repository.append_event("events", "evaluation", "completed", {}, db_path=path)
                running = client.get(url).json()
                self.assertEqual(running["status"], "running")
                self.assertEqual([e["seq"] for e in running["events"]], [1, 2])
                self.assertEqual(client.get(url + "?after=2").json()["events"], [])
                self.assertEqual(client.get(url + "?after=1").json()["next_after"], 2)
                repository.fail_interrupted(db_path=path)
                self.assertTrue(client.get(url).json()["finished"])
                self.assertEqual(client.get("/api/v1/analyses/missing/events").status_code, 404)
                self.assertEqual(client.get(url + "?after=-1").status_code, 422)

    def test_startup_finishes_interrupted_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "interrupted.sqlite3"
            initialize(path)
            repository.create_request("interrupted", "시험", db_path=path)
            repository.mark_running("interrupted", db_path=path)
            app = create_app(settings=ExecutionSettings(db_path=path), load_env=False)
            with TestClient(app) as client:
                response = client.get("/api/v1/analyses/interrupted")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "failed")
                self.assertEqual(response.json()["error"]["code"], "INTERRUPTED")

    def test_cors_and_request_id_are_exposed(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(
                settings=ExecutionSettings(db_path=Path(directory) / "cors.sqlite3"), load_env=False
            )
            with TestClient(app) as client:
                response = client.options(
                    "/api/v1/analyses",
                    headers={
                        "Origin": "http://localhost:3000",
                        "Access-Control-Request-Method": "POST",
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.headers["access-control-allow-origin"], "http://localhost:3000"
                )
                self.assertIn(
                    "DecisionResult", client.get("/openapi.json").json()["components"]["schemas"]
                )
