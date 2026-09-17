"""프론트엔드가 붙는 HTTP 경계를 검사합니다."""

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import main
from app.address import GeocodeError
from app.db import repository
from app.db.connection import connect
from app.main import allowed_origins
from app.schemas import DecisionResult
from app.services.settings import ExecutionSettings


class ApiTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "api.sqlite3"
        self.settings = ExecutionSettings(db_path=self.path)
        self.enterContext(
            patch("httpx.AsyncClient.send", side_effect=AssertionError("외부 연결 금지"))
        )
        self.client = self.enterContext(
            TestClient(main.create_app(settings=self.settings, load_env=False))
        )

    def test_health_is_open(self):
        for path in ("/health", "/api/v1/health"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "ok")

    def test_mock_analysis_returns_decision_result(self):
        response = self.client.post(
            "/api/v1/analyses?mock=true",
            json={"address": "서울특별시 노원구 한글비석로 242 삼부프라자 1층"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        DecisionResult.model_validate(payload)
        self.assertEqual(payload["agent_id"], "decision")
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertTrue(payload["recommendations"])
        self.assertEqual(len(payload["source_analyses"]), 3)
        self.assertEqual(response.headers["X-Request-ID"], payload["request_id"])
        saved = self.client.get(f"/api/v1/analyses/{payload['request_id']}")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["status"], "completed")
        self.assertEqual(saved.json()["result"]["recommendations"], payload["recommendations"])
        self.assertIsInstance(saved.json()["site"], dict)

    def test_failed_post_can_be_looked_up_and_errors_are_safe(self):
        from pydantic import ValidationError

        secret = "SECRET-URL-key"
        try:
            DecisionResult.model_validate({"secret": secret})
        except ValidationError as invalid:
            errors = [
                (GeocodeError("ADDRESS_AMBIGUOUS", secret), 400),
                (GeocodeError("UPSTREAM_FAILED", secret), 502),
                (RuntimeError(secret), 502),
                (ValueError(secret), 500),
                (invalid, 500),
                (sqlite3.OperationalError(secret), 500),
            ]
        for error, status in errors:
            with patch("app.services.analysis.run_react", new=AsyncMock(side_effect=error)):
                response = self.client.post(
                    "/api/v1/analyses?mock=true", json={"address": "시험 주소"}
                )
            self.assertEqual(response.status_code, status)
            self.assertNotIn(secret, response.text)
            saved = self.client.get(f"/api/v1/analyses/{response.headers['X-Request-ID']}")
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.json()["status"], "failed")
            self.assertIsInstance(saved.json()["error"], dict)
            self.assertNotIn(secret, saved.text)

    def test_legacy_record_is_not_revalidated_with_new_industry_rules(self):
        repository.create_request("legacy", "과거 주소", db_path=self.path)
        historical = {
            "request_id": "legacy",
            "address": "과거 주소",
            "recommendations": [{"category": {"middle": "옛날 커피전문점"}}],
        }
        with connect(self.path) as db:
            db.execute(
                "UPDATE analysis_requests SET status='completed', completed_at='2025-01-01', "
                "result_json=? WHERE request_id='legacy'",
                (json.dumps(historical),),
            )
        response = self.client.get("/api/v1/analyses/legacy")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], historical)
        self.assertEqual(self.client.get("/api/v1/analyses/missing").status_code, 404)

    def test_internal_analyzer_validation_error_returns_500_and_preserves_other_results(self):
        from app.mocks import mock_agents
        from app.schemas import AgentAnalysis

        async def invalid(task):
            return AgentAnalysis.model_validate({"request_id": task.request_id})

        agents = mock_agents()
        agents["floating_population"] = invalid
        with (
            patch("app.api.v1.routes.mock_agents", return_value=agents),
            patch("app.api.v1.routes.mock_generate") as decision,
        ):
            response = self.client.post("/api/v1/analyses?mock=true", json={"address": "시험 주소"})
        self.assertEqual(response.status_code, 500)
        decision.assert_not_called()
        request_id = response.headers["X-Request-ID"]
        self.assertEqual(
            self.client.get(f"/api/v1/analyses/{request_id}").json()["status"], "failed"
        )
        self.assertEqual(
            {
                row["agent_id"]
                for row in repository.list_agent_results(request_id, db_path=self.path)
            },
            {"business_lifecycle", "commercial_area"},
        )

    def test_factory_loads_environment_before_cors_and_exposes_request_id(self):
        def load():
            os.environ["CORS_ALLOW_ORIGINS"] = "https://loaded.example"

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(main, "load_environment", side_effect=load),
        ):
            with TestClient(main.create_app(settings=self.settings)) as client:
                response = client.get("/health", headers={"Origin": "https://loaded.example"})
        self.assertEqual(response.headers["access-control-allow-origin"], "https://loaded.example")
        self.assertIn("X-Request-ID", response.headers["access-control-expose-headers"])

    def test_blank_address_is_input_error(self):
        response = self.client.post("/api/v1/analyses?mock=true", json={"address": "   "})
        self.assertEqual(response.status_code, 400)

    def test_empty_address_is_rejected_before_any_call(self):
        response = self.client.post("/api/v1/analyses?mock=true", json={"address": ""})
        self.assertEqual(response.status_code, 422)

    def test_frontend_origin_is_allowed(self):
        response = self.client.options(
            "/api/v1/analyses",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:3000")

    def test_openapi_documents_the_contract(self):
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/api/v1/analyses", schema["paths"])
        self.assertIn("DecisionResult", schema["components"]["schemas"])

    def test_allowed_origins_reads_environment(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"CORS_ALLOW_ORIGINS": "https://a.example, https://b.example"}):
            self.assertEqual(allowed_origins(), ["https://a.example", "https://b.example"])


if __name__ == "__main__":
    unittest.main()
