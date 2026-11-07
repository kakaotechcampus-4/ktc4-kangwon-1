import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.v1.analyses import require_owner
from app.application import requests as analysis_requests
from app.infrastructure.settings import ExecutionSettings
from app.main import create_app
from tests.auth_fixture import login


class AnswerCheckTests(unittest.TestCase):
    def test_missing_request_is_not_found(self):
        with self.assertRaises(analysis_requests.AnswerRejected) as caught:
            analysis_requests.check_answers(None, "q", [], running=False)
        self.assertEqual(caught.exception.reason, "not_found")
        self.assertEqual(caught.exception.message, analysis_requests.NOT_FOUND)


class ProgressViewTests(unittest.TestCase):
    def test_accepted_job_without_row_is_pending(self):
        view = analysis_requests.progress_view("r", None, [], after=3, running=True)
        self.assertEqual(
            view,
            {
                "request_id": "r",
                "status": "pending",
                "finished": False,
                "events": [],
                "next_after": 3,
            },
        )

    def test_unknown_request_has_no_view(self):
        self.assertIsNone(analysis_requests.progress_view("r", None, [], after=0, running=False))


class DeletedRequestTests(unittest.TestCase):
    def test_request_gone_after_owner_check_is_404(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gone.sqlite3"
            app = create_app(settings=ExecutionSettings(db_path=path), load_env=False)
            login(app, path)
            app.dependency_overrides[require_owner] = lambda: None
            with TestClient(app) as client:
                for suffix in ("", "/facts", "/events"):
                    with self.subTest(suffix=suffix):
                        response = client.get(f"/api/v1/analyses/gone{suffix}")
                        self.assertEqual(response.status_code, 404)
                        self.assertEqual(response.json()["detail"], analysis_requests.NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
