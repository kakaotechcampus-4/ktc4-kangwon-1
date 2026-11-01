"""가입·로그인·세션을 진짜 쿠키 경로로 검증합니다.

tests/auth_fixture.py 는 의존성을 꺼 버려 current_user 의 실제 구현이 돌지 않습니다.
여기서는 오버라이드 없이 Set-Cookie 를 받아 그대로 다시 보냅니다.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.auth import SESSION_COOKIE_NAME
from app.services.settings import ExecutionSettings

ORIGIN = {"Origin": "http://localhost:3000"}
EMAIL = "owner@example.com"
PASSWORD = "testpassword1"


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "auth.sqlite3"
        app = create_app(settings=ExecutionSettings(db_path=self.path), load_env=False)
        # 메일은 보내지 않고 링크만 가로챕니다. 토큰은 해시로만 저장돼 DB에서 못 읽습니다.
        self.sent: list[tuple[str, str]] = []
        sender = self.enterContext(
            patch("app.services.auth.send_mail", new=AsyncMock(side_effect=self._capture))
        )
        self.sender = sender
        # 세션 쿠키는 Secure 라 http 로는 전송되지 않습니다. 운영과 같은 https 로 띄웁니다.
        self.client = self.enterContext(TestClient(app, base_url="https://testserver"))

    async def _capture(self, to, subject, html, settings, *, client=None):
        self.sent.append((to, html))

    def _link_token(self) -> str:
        _, html = self.sent[-1]
        start = html.index('href="') + len('href="')
        url = html[start : html.index('"', start)]
        return parse_qs(urlsplit(url).query)["token"][0]

    def signup(self, email=EMAIL, password=PASSWORD):
        return self.client.post(
            "/api/v1/auth/signup",
            json={"email": email, "password": password, "display_name": "임대인"},
            headers=ORIGIN,
        )

    # ── 가입 ────────────────────────────────────────────────────────────
    def test_signup_sets_session_and_requires_verification(self):
        response = self.signup()
        self.assertEqual(response.status_code, 201, response.text)
        self.assertIn(SESSION_COOKIE_NAME, self.client.cookies)

        me = self.client.get("/api/v1/auth/me")
        self.assertEqual(me.status_code, 200, me.text)
        body = me.json()
        self.assertEqual(body["email"], EMAIL)
        self.assertFalse(body["email_verified"])
        self.assertTrue(body["needs_verification"])
        self.assertNotIn("password_hash", body)

    def test_duplicate_email_is_409(self):
        self.signup()
        self.client.cookies.clear()
        self.assertEqual(self.signup().status_code, 409)

    def test_short_password_is_422(self):
        self.assertEqual(self.signup(password="short").status_code, 422)

    def test_malformed_email_is_422(self):
        self.assertEqual(self.signup(email="not-an-email").status_code, 422)

    # ── 메일 확인과 분석 실행 ───────────────────────────────────────────
    def test_unverified_account_cannot_start_analysis(self):
        self.signup()
        blocked = self.client.post(
            "/api/v1/analyses?mock=true", json={"address": "시험"}, headers=ORIGIN
        )
        self.assertEqual(blocked.status_code, 403, blocked.text)

        token = self._link_token()
        verified = self.client.post(
            "/api/v1/auth/verify-email", json={"token": token}, headers=ORIGIN
        )
        self.assertEqual(verified.status_code, 200, verified.text)
        self.assertTrue(self.client.get("/api/v1/auth/me").json()["email_verified"])

        allowed = self.client.post(
            "/api/v1/analyses?mock=true", json={"address": "시험"}, headers=ORIGIN
        )
        self.assertEqual(allowed.status_code, 200, allowed.text)

    def test_verification_token_is_single_use(self):
        self.signup()
        token = self._link_token()
        self.client.post("/api/v1/auth/verify-email", json={"token": token}, headers=ORIGIN)
        again = self.client.post("/api/v1/auth/verify-email", json={"token": token}, headers=ORIGIN)
        self.assertEqual(again.status_code, 400)

    # ── 로그인 ──────────────────────────────────────────────────────────
    def test_login_rejects_wrong_password_with_same_message(self):
        self.signup()
        self.client.cookies.clear()
        wrong = self.client.post(
            "/api/v1/auth/login",
            json={"email": EMAIL, "password": "wrongpassword"},
            headers=ORIGIN,
        )
        missing = self.client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": PASSWORD},
            headers=ORIGIN,
        )
        self.assertEqual((wrong.status_code, missing.status_code), (401, 401))
        # 가입 여부가 응답 차이로 새 나가면 안 됩니다.
        self.assertEqual(wrong.json()["detail"], missing.json()["detail"])

    def test_repeated_failures_are_throttled(self):
        self.signup()
        self.client.cookies.clear()
        codes = [
            self.client.post(
                "/api/v1/auth/login",
                json={"email": EMAIL, "password": "wrongpassword"},
                headers=ORIGIN,
            ).status_code
            for _ in range(6)
        ]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5], 429)

    def test_logout_clears_the_session(self):
        self.signup()
        self.assertEqual(self.client.post("/api/v1/auth/logout", headers=ORIGIN).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)

    def test_me_without_cookie_is_401(self):
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)

    def test_forged_cookie_is_rejected(self):
        self.client.cookies.set(SESSION_COOKIE_NAME, "made-up-token")
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)

    # ── 비밀번호 재설정 ─────────────────────────────────────────────────
    def test_forgot_password_hides_whether_the_account_exists(self):
        self.signup()
        known = self.client.post(
            "/api/v1/auth/password/forgot", json={"email": EMAIL}, headers=ORIGIN
        )
        unknown = self.client.post(
            "/api/v1/auth/password/forgot", json={"email": "nobody@example.com"}, headers=ORIGIN
        )
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.json(), unknown.json())

    def test_reset_changes_password_and_drops_other_sessions(self):
        self.signup()
        self.client.post("/api/v1/auth/password/forgot", json={"email": EMAIL}, headers=ORIGIN)
        token = self._link_token()
        reset = self.client.post(
            "/api/v1/auth/password/reset",
            json={"token": token, "new_password": "brandnewpassword"},
            headers=ORIGIN,
        )
        self.assertEqual(reset.status_code, 200, reset.text)
        # 비밀번호가 샜을 수 있으니 가입 때 받은 세션도 끊겨야 합니다.
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=ORIGIN
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/login",
                json={"email": EMAIL, "password": "brandnewpassword"},
                headers=ORIGIN,
            ).status_code,
            200,
        )

    # ── CSRF ────────────────────────────────────────────────────────────
    def test_write_without_origin_is_403(self):
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/signup", json={"email": EMAIL, "password": PASSWORD}
            ).status_code,
            403,
        )

    def test_write_from_foreign_origin_is_403(self):
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/signup",
                json={"email": EMAIL, "password": PASSWORD},
                headers={"Origin": "https://evil.example"},
            ).status_code,
            403,
        )

    def test_health_stays_open(self):
        # 여기서 막히면 deploy.sh 헬스체크가 실패해 배포가 전환되지 않습니다.
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/health").status_code, 200)


if __name__ == "__main__":
    unittest.main()
