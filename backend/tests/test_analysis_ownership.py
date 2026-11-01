"""분석 요청이 만든 사람에게만 보이는지 검증합니다."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import repository
from app.db.connection import connect, initialize
from app.main import create_app
from app.services.auth import SESSION_COOKIE_NAME
from app.services.settings import ExecutionSettings
from tests.auth_fixture import create_user

ORIGIN = {"Origin": "http://localhost:3000"}


def _session_cookie(user_id, path):
    from app.db.repository import sessions as session_repo

    token, _ = session_repo.create_session(user_id, db_path=path)
    return token


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "owner.sqlite3"
        initialize(self.path)
        self.owner = create_user(self.path, email="owner@example.com")
        self.stranger = create_user(self.path, email="stranger@example.com")
        app = create_app(settings=ExecutionSettings(db_path=self.path), load_env=False)
        self.client = self.enterContext(TestClient(app, base_url="https://testserver"))

    def as_user(self, user):
        self.client.cookies.set(SESSION_COOKIE_NAME, _session_cookie(user["user_id"], self.path))

    def create_analysis(self):
        self.as_user(self.owner)
        response = self.client.post(
            "/api/v1/analyses?mock=true", json={"address": "시험"}, headers=ORIGIN
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["request_id"]

    # ── 로그인 없으면 못 돌림 ───────────────────────────────────────────
    def test_anonymous_cannot_start_analysis(self):
        response = self.client.post(
            "/api/v1/analyses?mock=true", json={"address": "시험"}, headers=ORIGIN
        )
        self.assertEqual(response.status_code, 401)
        with connect(self.path) as db:
            # 막힌 요청이 DB에 흔적을 남기면 안 됩니다.
            self.assertEqual(db.execute("SELECT count(*) FROM analysis_requests").fetchone()[0], 0)

    def test_anonymous_cannot_read_building_registry(self):
        response = self.client.get(
            "/api/v1/building-registry", params={"address": "서울 어딘가", "mock": True}
        )
        self.assertEqual(response.status_code, 401)

    def test_unverified_account_is_403_not_401(self):
        unverified = create_user(self.path, email="new@example.com", verified=False)
        self.as_user(unverified)
        response = self.client.post(
            "/api/v1/analyses?mock=true", json={"address": "시험"}, headers=ORIGIN
        )
        self.assertEqual(response.status_code, 403)

    # ── 소유자만 조회 ───────────────────────────────────────────────────
    def test_owner_sees_every_view_of_the_request(self):
        request_id = self.create_analysis()
        for suffix in ("", "/events", "/facts"):
            with self.subTest(view=suffix or "detail"):
                response = self.client.get(f"/api/v1/analyses/{request_id}{suffix}")
                self.assertEqual(response.status_code, 200, response.text)

    def test_stranger_gets_404_not_403(self):
        request_id = self.create_analysis()
        self.as_user(self.stranger)
        for suffix in ("", "/events", "/facts"):
            with self.subTest(view=suffix or "detail"):
                response = self.client.get(f"/api/v1/analyses/{request_id}{suffix}")
                # 403이면 그 ID가 존재한다는 사실이 새 나갑니다.
                self.assertEqual(response.status_code, 404, response.text)

    def test_anonymous_gets_404_for_owned_request(self):
        request_id = self.create_analysis()
        self.client.cookies.clear()
        self.assertEqual(self.client.get(f"/api/v1/analyses/{request_id}").status_code, 404)

    def test_stranger_cannot_answer_questions(self):
        request_id = self.create_analysis()
        self.as_user(self.stranger)
        response = self.client.post(
            f"/api/v1/analyses/{request_id}/answers",
            json={"question_session_id": "q", "answers": {"a": "b"}},
            headers=ORIGIN,
        )
        self.assertEqual(response.status_code, 404)

    def test_missing_request_is_404(self):
        self.as_user(self.owner)
        self.assertEqual(self.client.get("/api/v1/analyses/nope").status_code, 404)

    # ── 인증 이전 자료 ──────────────────────────────────────────────────
    def test_requests_from_before_auth_stay_readable(self):
        repository.create_request("legacy", "옛 요청", db_path=self.path)
        with connect(self.path) as db:
            db.execute(
                "UPDATE analysis_requests SET created_at=? WHERE request_id='legacy'",
                ("2026-01-01T00:00:00+00:00",),
            )
        self.as_user(self.stranger)
        self.assertEqual(self.client.get("/api/v1/analyses/legacy").status_code, 200)

    def test_ownerless_request_made_after_the_cutoff_is_hidden(self):
        # 소유자 기록이 빠진 새 요청까지 열어 두면 영구 구멍이 됩니다.
        repository.create_request("orphan", "소유자 없음", db_path=self.path)
        self.as_user(self.stranger)
        self.assertEqual(self.client.get("/api/v1/analyses/orphan").status_code, 404)

    # ── 내 기록 ─────────────────────────────────────────────────────────
    def test_my_analyses_lists_only_my_own(self):
        request_id = self.create_analysis()
        mine = self.client.get("/api/v1/me/analyses").json()
        self.assertEqual(mine["total"], 1)
        self.assertEqual([item["request_id"] for item in mine["items"]], [request_id])

        self.as_user(self.stranger)
        self.assertEqual(self.client.get("/api/v1/me/analyses").json()["total"], 0)

    def test_my_analyses_needs_login(self):
        self.assertEqual(self.client.get("/api/v1/me/analyses").status_code, 401)

    def test_my_analyses_pages(self):
        self.as_user(self.owner)
        for index in range(3):
            self.client.post(
                "/api/v1/analyses?mock=true", json={"address": f"시험{index}"}, headers=ORIGIN
            )
        page = self.client.get("/api/v1/me/analyses?limit=2&offset=0").json()
        self.assertEqual((page["total"], len(page["items"])), (3, 2))
        rest = self.client.get("/api/v1/me/analyses?limit=2&offset=2").json()
        self.assertEqual(len(rest["items"]), 1)


if __name__ == "__main__":
    unittest.main()
