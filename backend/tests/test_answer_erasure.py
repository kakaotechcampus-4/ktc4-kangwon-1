import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.infrastructure.persistence.repository import erasure
from app.infrastructure.settings import ExecutionSettings
from app.main import create_app
from tests.auth_fixture import login

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "erase_user_answers.py"
SENTINEL = "홍길동 010-1234-5678"
MULTILINE = '홍길동 "010-1234-5678"\n두 번째 줄'
ERASED = "[삭제됨]"


def _escaped(text, ascii):
    return json.dumps(text, ensure_ascii=ascii)[1:-1]


def _forms(text):
    once = {_escaped(text, flag) for flag in (True, False)}
    twice = {_escaped(form, flag) for form in once for flag in (True, False)}
    return {text} | once | twice


def _rows(path, forms):
    forms = sorted(forms)
    total = 0
    with closing(sqlite3.connect(path)) as db:
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        for (table,) in tables:
            columns = [
                column[1]
                for column in db.execute(f'PRAGMA table_info("{table}")')
                if "TEXT" in column[2].upper()
            ]
            if not columns:
                continue
            match = " OR ".join(f'instr("{column}", ?) > 0' for column in columns for _ in forms)
            total += db.execute(
                f'SELECT count(*) FROM "{table}" WHERE {match}',
                [form for _ in columns for form in forms],
            ).fetchone()[0]
    return total


def _hits(path, text):
    return _rows(path, _forms(text))


def _triggers(path):
    with closing(sqlite3.connect(path)) as db:
        return db.execute(
            "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger' ORDER BY name"
        ).fetchall()


def _add_event(path, request_id, detail_text):
    with closing(sqlite3.connect(path)) as db:
        db.execute(
            "INSERT INTO analysis_events(request_id,seq,stage,event,detail_json,created_at) "
            "SELECT ?, COALESCE(max(seq), 0) + 1, 'note', 'completed', ?, "
            "'2026-11-08T00:00:00+00:00' FROM analysis_events WHERE request_id=?",
            (request_id, detail_text, request_id),
        )
        db.commit()


def _answered_request(client, text):
    waiting = client.post(
        "/api/v1/analyses?mock=true", json={"address": "시험", "allow_questions": True}
    ).json()
    response = client.post(
        f"/api/v1/analyses/{waiting['request_id']}/answers?mock=true",
        json={
            "question_session_id": waiting["question_session_id"],
            "answers": {q["field"]: text for q in waiting["questions"]},
        },
    )
    assert response.status_code == 200, response.text
    return waiting["request_id"]


class AnswerErasureTests(unittest.TestCase):
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
        login(app, cls.template)
        with TestClient(app) as client:
            cls.request_id = _answered_request(client, SENTINEL)
            cls.multiline_id = _answered_request(client, MULTILINE)
        _add_event(cls.template, cls.request_id, json.dumps({"note": SENTINEL}))

    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "answers.sqlite3"
        with (
            closing(sqlite3.connect(self.template)) as source,
            closing(sqlite3.connect(self.path)) as target,
        ):
            source.backup(target)

    def read(self, request_id):
        app = create_app(settings=ExecutionSettings(db_path=self.path), load_env=False)
        login(app, self.path)
        client = self.enterContext(TestClient(app))
        found = {}
        for suffix in ("", "/facts", "/events"):
            with self.subTest(read=suffix):
                response = client.get(f"/api/v1/analyses/{request_id}{suffix}")
                self.assertEqual(response.status_code, 200, response.text)
                found[suffix] = response.json()
        return found

    def test_korean_answer_is_erased_even_when_json_escaped(self):
        self.assertGreater(_hits(self.path, SENTINEL), 0)
        self.assertGreater(_rows(self.path, {_escaped(SENTINEL, True)}), 0)
        changed = erasure.erase_user_answers(self.request_id, db_path=self.path)
        self.assertGreater(changed, 0)
        self.assertEqual(_hits(self.path, SENTINEL), 0)
        found = self.read(self.request_id)
        self.assertIn(ERASED, [fact["value"] for fact in found["/facts"]["facts"]])
        notes = [e["detail"] for e in found["/events"]["events"] if e["stage"] == "note"]
        self.assertEqual(notes, [{"note": ERASED}])
        self.assertEqual(_hits(self.path, MULTILINE), _hits(self.template, MULTILINE))

    def test_multiline_answer_is_erased_inside_nested_json(self):
        nested = _escaped(_escaped(MULTILINE, False), False)
        self.assertGreater(_rows(self.path, {nested}), 0)
        self.assertGreater(erasure.erase_user_answers(self.multiline_id, db_path=self.path), 0)
        self.assertEqual(_hits(self.path, MULTILINE), 0)
        with closing(sqlite3.connect(self.path)) as db:
            (state,) = db.execute(
                "SELECT state_json FROM agentic_runs WHERE request_id=?", (self.multiline_id,)
            ).fetchone()
        replies = [
            json.loads(message["content"])
            for message in json.loads(state)["messages"]
            if message["role"] == "tool" and ERASED in message["content"]
        ]
        self.assertEqual([set(r["data"]["answers"].values()) for r in replies], [{ERASED}])
        self.read(self.multiline_id)

    def test_triggers_are_restored(self):
        before = _triggers(self.path)
        erasure.erase_user_answers(self.request_id, db_path=self.path)
        self.assertEqual(_triggers(self.path), before)
        with (
            closing(sqlite3.connect(self.path)) as db,
            self.assertRaisesRegex(sqlite3.IntegrityError, "facts are immutable"),
        ):
            db.execute("UPDATE facts SET unit='바꿈'")

    def test_failure_rolls_back_and_keeps_triggers(self):
        before, hits = _triggers(self.path), _hits(self.path, SENTINEL)
        rewrite = erasure._rewrite
        seen = []

        def fail_second(db, *args):
            query = "SELECT count(*) FROM sqlite_master WHERE type='trigger'"
            seen.append(db.execute(query).fetchone()[0])
            if len(seen) > 1:
                raise RuntimeError("시험용 실패")
            rewrite(db, *args)

        with (
            patch.object(erasure, "_rewrite", side_effect=fail_second),
            self.assertRaisesRegex(RuntimeError, "시험용 실패"),
        ):
            erasure.erase_user_answers(self.request_id, db_path=self.path)
        self.assertEqual(len(seen), 2)
        self.assertLess(seen[-1], len(before))
        self.assertEqual(_hits(self.path, SENTINEL), hits)
        self.assertEqual(_triggers(self.path), before)

    def test_unknown_request_changes_nothing(self):
        before, hits = _triggers(self.path), _hits(self.path, SENTINEL)
        self.assertEqual(erasure.erase_user_answers("missing", db_path=self.path), 0)
        self.assertEqual(_hits(self.path, SENTINEL), hits)
        self.assertEqual(_triggers(self.path), before)

    def test_other_request_and_account_keep_same_text(self):
        _add_event(self.path, self.request_id, json.dumps({"note": MULTILINE}, ensure_ascii=False))
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE users SET display_name=?", (MULTILINE,))
            db.commit()
        erasure.erase_user_answers(self.multiline_id, db_path=self.path)
        self.assertEqual(_hits(self.path, MULTILINE), 2)

    def test_script_prints_changed_count(self):
        def run(request_id):
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(self.path), request_id],
                cwd=BACKEND,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.splitlines()

        self.assertEqual(run("missing"), ["0"])
        printed = run(self.request_id)
        self.assertEqual(len(printed), 1)
        self.assertGreater(int(printed[0]), 0)
        self.assertEqual(_hits(self.path, SENTINEL), 0)
        self.assertEqual(run(self.request_id), ["0"])


if __name__ == "__main__":
    unittest.main()
