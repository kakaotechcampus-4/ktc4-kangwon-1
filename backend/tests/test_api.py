"""프론트엔드가 붙는 HTTP 경계를 검사합니다."""

import unittest

from fastapi.testclient import TestClient

from app.main import allowed_origins, app
from app.schemas import DecisionResult


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

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
