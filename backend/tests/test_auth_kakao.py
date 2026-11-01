"""카카오 로그인을 외부 연결 없이 검증합니다. 실패는 모두 화면으로 돌려보냅니다."""

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi.testclient import TestClient

from app.config import KakaoOAuthSettings
from app.db.connection import connect
from app.db.repository import sessions as session_repo
from app.main import create_app
from app.services.auth import SESSION_COOKIE_NAME
from app.services.settings import ExecutionSettings

FRONTEND = "https://app.example.test"
KAKAO_ID = 3_481_900_000_000_000_001  # int64. 문자열로 보관돼야 자릿수가 안 깎입니다.


def _transport(token_status=200, profile_status=200, token_body=None, profile_body=None):
    def handle(request: httpx.Request) -> httpx.Response:
        if "oauth/token" in str(request.url):
            return httpx.Response(token_status, json=token_body or {"access_token": "kakao-access"})
        return httpx.Response(
            profile_status,
            json=profile_body
            or {
                "id": KAKAO_ID,
                "kakao_account": {"profile": {"nickname": "임대인", "profile_image_url": None}},
            },
        )

    return httpx.MockTransport(handle)


class KakaoLoginTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "kakao.sqlite3"
        self.app = create_app(settings=ExecutionSettings(db_path=self.path), load_env=False)
        self.app.state.kakao_settings = KakaoOAuthSettings(
            client_id="rest-key",
            client_secret="secret",
            redirect_uri="https://api.example.test/api/v1/auth/kakao/callback",
        )
        self.app.state.auth_settings = type(self.app.state.auth_settings)(
            frontend_base_url=FRONTEND, cookie_secure=True
        )
        self.client = self.enterContext(
            TestClient(self.app, base_url="https://testserver", follow_redirects=False)
        )

    def start(self, next_path="/vacancy-input") -> str:
        response = self.client.get(f"/api/v1/auth/kakao/login?next={next_path}")
        self.assertEqual(response.status_code, 302)
        location = response.headers["location"]
        self.assertTrue(location.startswith("https://kauth.kakao.com/oauth/authorize"))
        return parse_qs(urlsplit(location).query)["state"][0]

    def callback(self, state, code="auth-code", **transport):
        with patch("httpx.AsyncClient", _patched_client(_transport(**transport))):
            return self.client.get(f"/api/v1/auth/kakao/callback?code={code}&state={state}")

    # ── 정상 흐름 ───────────────────────────────────────────────────────
    def test_login_creates_account_and_returns_to_next(self):
        state = self.start()
        response = self.callback(state)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], f"{FRONTEND}/vacancy-input")
        self.assertIn(SESSION_COOKIE_NAME, self.client.cookies)

        me = self.client.get("/api/v1/auth/me")
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["display_name"], "임대인")
        # 소셜 계정은 비밀번호가 없어 메일 확인을 요구하지 않습니다.
        self.assertFalse(me.json()["needs_verification"])

    def test_kakao_id_keeps_full_precision(self):
        # 카카오 id 는 int64 입니다. 숫자로 보관하면 자릿수가 깎일 수 있어 문자열로 둡니다.
        self.callback(self.start())
        with connect(self.path) as db:
            row = db.execute("SELECT provider_user_id FROM user_identities").fetchone()
        self.assertEqual(row["provider_user_id"], str(KAKAO_ID))

    def test_second_login_reuses_the_same_account(self):
        self.callback(self.start())
        self.client.cookies.clear()
        self.callback(self.start())
        with connect(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM users").fetchone()[0], 1)

    def test_missing_profile_fields_are_allowed(self):
        state = self.start()
        response = self.callback(state, profile_body={"id": KAKAO_ID})
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.client.get("/api/v1/auth/me").json()["display_name"])

    # ── state ───────────────────────────────────────────────────────────
    def test_state_is_single_use(self):
        state = self.start()
        self.callback(state)
        self.client.cookies.clear()
        again = self.callback(state)
        self.assertEqual(again.headers["location"], f"{FRONTEND}/login?error=expired")

    def test_unknown_state_is_rejected(self):
        response = self.callback("never-issued")
        self.assertEqual(response.headers["location"], f"{FRONTEND}/login?error=expired")

    def test_external_next_is_dropped(self):
        state = self.start(next_path="https://evil.example/steal")
        response = self.callback(state)
        self.assertEqual(response.headers["location"], f"{FRONTEND}/")

    # ── 실패는 전부 화면으로 ────────────────────────────────────────────
    def test_user_cancelled_goes_to_login(self):
        response = self.client.get("/api/v1/auth/kakao/callback?error=access_denied")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], f"{FRONTEND}/login?error=cancelled")

    def test_token_rejection_goes_to_login(self):
        state = self.start()
        response = self.callback(state, token_status=400, token_body={"error": "invalid_grant"})
        self.assertEqual(response.headers["location"], f"{FRONTEND}/login?error=failed")

    def test_kakao_outage_goes_to_login(self):
        state = self.start()
        response = self.callback(state, token_status=503, token_body={})
        self.assertEqual(response.headers["location"], f"{FRONTEND}/login?error=unavailable")

    def test_profile_rejection_goes_to_login(self):
        state = self.start()
        response = self.callback(state, profile_status=401, profile_body={})
        self.assertEqual(response.headers["location"], f"{FRONTEND}/login?error=failed")

    def test_missing_configuration_does_not_leak_a_stack_trace(self):
        self.app.state.kakao_settings = KakaoOAuthSettings()
        response = self.client.get("/api/v1/auth/kakao/login?next=/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], f"{FRONTEND}/login?error=unavailable")

    def test_expired_state_is_not_consumable(self):
        # 만료 시각을 과거로 두고 발급하면 그 state 는 바로 죽어 있어야 합니다.
        with patch.object(session_repo, "OAUTH_STATE_TTL", timedelta(seconds=-1)):
            state = session_repo.create_oauth_state("/", db_path=self.path)
        self.assertIsNone(session_repo.consume_oauth_state(state, db_path=self.path))


def _patched_client(transport):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    return factory


if __name__ == "__main__":
    unittest.main()
