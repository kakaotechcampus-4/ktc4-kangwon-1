import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.infrastructure.persistence.repository import sessions, users
from app.infrastructure.settings import ExecutionSettings
from app.main import create_app
from tests.auth_fixture import create_user, login

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "withdraw_user.py"
ANSWER = "홍길동 010-1234-5678"
ACCOUNT_TABLES = (
    "users",
    "user_sessions",
    "user_identities",
    "terms_agreements",
    "analysis_owners",
    "email_tokens",
)
REFUSED = "분석이 끝난 뒤에 지울 수 있습니다."


def _account_rows(path, user_id):
    with closing(sqlite3.connect(path)) as db:
        return {
            table: db.execute(
                f'SELECT count(*) FROM "{table}" WHERE user_id=?', (user_id,)
            ).fetchone()[0]
            for table in ACCOUNT_TABLES
        }


def _answers(path, request_id):
    with closing(sqlite3.connect(path)) as db:
        (text,) = db.execute(
            "SELECT answers_json FROM agentic_questions WHERE request_id=?", (request_id,)
        ).fetchone()
    return text


def _run_script(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        cwd=BACKEND,
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=60,
    )


class WithdrawUserScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.enterClassContext(
            patch(
                "httpx.AsyncHTTPTransport.handle_async_request",
                side_effect=AssertionError("외부 연결 금지"),
            )
        )
        directory = cls.enterClassContext(tempfile.TemporaryDirectory())
        cls.template = Path(directory) / "template.sqlite3"
        app = create_app(settings=ExecutionSettings(db_path=cls.template), load_env=False)
        cls.user_id = login(app, cls.template)["user_id"]
        with TestClient(app) as client:
            waiting = client.post(
                "/api/v1/analyses?mock=true", json={"address": "시험", "allow_questions": True}
            ).json()
            cls.request_id = waiting["request_id"]
            response = client.post(
                f"/api/v1/analyses/{cls.request_id}/answers?mock=true",
                json={
                    "question_session_id": waiting["question_session_id"],
                    "answers": {q["field"]: ANSWER for q in waiting["questions"]},
                },
            )
            assert response.status_code == 200, response.text
        users.attach_identity("kakao", "12345", cls.user_id, db_path=cls.template)
        sessions.create_session(cls.user_id, db_path=cls.template)
        sessions.create_email_token(cls.user_id, "verify_email", db_path=cls.template)
        cls.other_id = create_user(cls.template, email="other@example.com")["user_id"]
        sessions.create_session(cls.other_id, db_path=cls.template)

    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "withdraw.sqlite3"
        with (
            closing(sqlite3.connect(self.template)) as source,
            closing(sqlite3.connect(self.path)) as target,
        ):
            source.backup(target)

    def assert_withdrawn(self):
        self.assertEqual(set(_account_rows(self.path, self.user_id).values()), {0})
        self.assertEqual(
            _account_rows(self.path, self.other_id),
            _account_rows(self.template, self.other_id),
        )
        with closing(sqlite3.connect(self.path)) as db:
            found = db.execute(
                "SELECT count(*) FROM analysis_requests WHERE request_id=?", (self.request_id,)
            ).fetchone()[0]
        self.assertEqual(found, 1)

    def test_account_rows_exist_before_withdrawal(self):
        self.assertNotIn(0, _account_rows(self.template, self.user_id).values())

    def test_withdraw_removes_account_and_keeps_answers(self):
        result = _run_script(self.path, self.user_id)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["탈퇴했습니다: 질문 답을 지운 분석 0건, 연결을 끊은 분석 1건"],
        )
        self.assert_withdrawn()
        self.assertIn(ANSWER, _answers(self.path, self.request_id))

    def test_erase_answers_flag_erases_before_withdrawal(self):
        result = _run_script(self.path, self.user_id, "--erase-answers")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["탈퇴했습니다: 질문 답을 지운 분석 1건, 연결을 끊은 분석 1건"],
        )
        self.assert_withdrawn()
        self.assertNotIn(ANSWER, _answers(self.path, self.request_id))

    def test_unfinished_analysis_keeps_account(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(
                "UPDATE analysis_requests SET status='running', completed_at=NULL, "
                "result_json=NULL WHERE request_id=?",
                (self.request_id,),
            )
            db.commit()
        before = _account_rows(self.path, self.user_id)
        result = _run_script(self.path, self.user_id, "--erase-answers")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn(REFUSED, result.stderr)
        self.assertEqual(_account_rows(self.path, self.user_id), before)
        self.assertIn(ANSWER, _answers(self.path, self.request_id))

    def test_unknown_user_changes_nothing(self):
        before = _account_rows(self.path, self.user_id)
        result = _run_script(self.path, "missing")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("missing", result.stderr)
        self.assertEqual(_account_rows(self.path, self.user_id), before)

    def test_missing_arguments_print_usage(self):
        for args in ((), (self.path,), (self.path, "--erase-answers")):
            with self.subTest(args=args):
                result = _run_script(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("사용법: "), result.stderr)


if __name__ == "__main__":
    unittest.main()
