import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.ai import read_tools
from app.ai.tool_contracts import GetFactsInput
from app.application.errors import AnalysisConflictError
from app.application.space import CONFIRMED_UNIT
from app.domain.contracts import ToolReply
from app.infrastructure.persistence.raw_capture import CaptureScope
from app.infrastructure.persistence.repository import erasure
from app.infrastructure.settings import ExecutionSettings
from app.main import create_app
from app.shared.canonical import canonical_hash
from tests.auth_fixture import login

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "erase_user_answers.py"
SENTINEL = "홍길동 010-1234-5678"
MULTILINE = '홍길동 "010-1234-5678"\n두 번째 줄'
SHARED = "같은 답 02-555-0000"
VERDICT = "해당 없음"
SHORT = "주방 없음"
PHONE = "010-1234-5678"
PHONE_NOTE = {"note": "연락처 010-1234-5678 로 연락"}
FOOD = "음식점"
FOOD_NOTE = {
    "kakao_category": "음식점 > 한식",
    "indsSclsNm": "한식 음식점",
    "note": "일반음식점 허가",
    "summary": "주변에 음식점이 많아요",
}
SPACE = {"floor": "지하 1층", "exclusive_area_m2": 84.5}
SPACE_ANSWER = "김영희 010-2222-3333"
ERASED = "[삭제됨]"
PROSE_TABLES = {
    "agentic_reports",
    "agentic_reviews",
    "agentic_runs",
    "analysis_events",
    "analysis_requests",
    "advisor_consults",
    "decision_failures",
    "tool_calls",
}
LABEL_KEY = re.compile(r"category|[a-z0-9](?:Nm|Cd)$|(?:^|_)(?:names?|ids?|codes?)$")
REFUSED = "분석이 끝난 뒤에 지울 수 있습니다."
OWNED = {
    "raw_payloads": "payload_hash IN (SELECT payload_hash FROM raw_responses WHERE request_id=:id)",
    "raw_rows": "raw_row_id IN (SELECT e.raw_row_id FROM raw_response_rows e "
    "JOIN raw_responses p USING(response_id) WHERE p.request_id=:id)",
}
RAW_PAYLOADS = (
    "SELECT p.response_id, b.response_json FROM raw_responses p "
    "JOIN raw_payloads b USING(payload_hash) WHERE p.request_id=? ORDER BY p.rowid"
)
RAW_ROWS = (
    "SELECT e.response_id, r.row_index, r.natural_key, r.raw_json FROM raw_response_rows e "
    "JOIN raw_responses p USING(response_id) JOIN raw_rows r USING(raw_row_id) "
    "WHERE p.request_id=? ORDER BY e.response_id, r.row_index"
)
LINKED = {
    "scores": "SELECT s.* FROM scores s JOIN score_snapshots n USING(score_snapshot_id) "
    "WHERE n.request_id=? ORDER BY s.rowid",
    "fact_sources": "SELECT s.fact_id, s.field_pointer FROM fact_sources s "
    "JOIN facts f USING(fact_id) WHERE f.request_id=? ORDER BY s.fact_id, s.field_pointer",
}
MOVED_COLUMNS = {("raw_responses", "payload_hash")}
CONFIRMED_SPACE = (
    "SELECT f.*, r.raw_json, p.response_id, b.response_json FROM facts f "
    "JOIN fact_sources s USING(fact_id) JOIN raw_rows r USING(raw_row_id) "
    "JOIN raw_payloads b ON b.payload_hash=r.payload_hash "
    "JOIN raw_responses p ON p.payload_hash=b.payload_hash AND p.request_id=f.request_id "
    "WHERE f.request_id=? AND f.unit=? ORDER BY f.fact_id, p.response_id"
)


def _escaped(text, ascii):
    return json.dumps(text, ensure_ascii=ascii)[1:-1]


def _forms(text):
    once = {_escaped(text, flag) for flag in (True, False)}
    twice = {_escaped(form, flag) for form in once for flag in (True, False)}
    return {text} | once | twice


def _rows(path, forms, request_id=None):
    forms = sorted(forms)
    params = {"id": request_id} | {f"f{index}": form for index, form in enumerate(forms)}
    total = 0
    with closing(sqlite3.connect(path)) as db:
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        for (table,) in tables:
            info = db.execute(f'PRAGMA table_info("{table}")').fetchall()
            owned = "request_id=:id" if "request_id" in [c[1] for c in info] else None
            owned = OWNED.get(table, owned) if request_id else "1"
            columns = [column[1] for column in info if "TEXT" in column[2].upper()]
            if not columns or owned is None:
                continue
            match = " OR ".join(
                f'instr("{column}", :f{index}) > 0'
                for column in columns
                for index in range(len(forms))
            )
            total += db.execute(
                f'SELECT count(*) FROM "{table}" WHERE ({owned}) AND ({match})', params
            ).fetchone()[0]
    return total


def _hits(path, text, request_id=None):
    return _rows(path, _forms(text), request_id)


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


def _evidence(path, request_id):
    with closing(sqlite3.connect(path)) as db:
        rows = db.execute(
            "SELECT f.value_json, r.raw_json, s.field_pointer FROM facts f "
            "JOIN fact_sources s USING(fact_id) JOIN raw_rows r USING(raw_row_id) "
            "WHERE f.request_id=? AND f.source='user'",
            (request_id,),
        ).fetchall()
    return [(json.loads(value), json.loads(raw)[pointer[1:]]) for value, raw, pointer in rows]


def _wrong_content_hashes(path):
    with closing(sqlite3.connect(path)) as db:
        stored = [
            *db.execute("SELECT payload_hash, response_json FROM raw_payloads").fetchall(),
            *db.execute("SELECT row_hash, raw_json FROM raw_rows").fetchall(),
        ]
    return [digest for digest, text in stored if digest != canonical_hash(json.loads(text))]


def _container(value):
    try:
        parsed = json.loads(value)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict | list) else None


def _walk(path, value, fields, kept, answers):
    if isinstance(value, dict):
        for key, item in value.items():
            _walk((*path, key), item, fields, kept, answers)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk((*path, index), item, fields, kept, answers)
    elif isinstance(value, str) and _container(value) is not None:
        _walk((*path, "<json>"), _container(value), fields, kept, answers)
    elif isinstance(value, str) and path[-1] in fields and _holds_answers(path):
        answers.append(value)
    else:
        kept.append((path, (type(value).__name__, value)))


def _word(answer):
    tail = r"(?![0-9A-Za-z_])" if re.fullmatch(r"[0-9A-Za-z_]", answer[-1]) else ""
    return re.compile(r"(?<![가-힣0-9A-Za-z_])" + re.escape(answer) + tail)


def _quotable(path):
    labels = [step for step in path if isinstance(step, str) and LABEL_KEY.search(step)]
    return path[0] in PROSE_TABLES and not labels


def _bad_changes(kept, after, answer):
    word = _word(answer)
    return [
        (path, before, now)
        for (path, before), (_, now) in zip(kept, after, strict=True)
        if now != before
        and not (
            _quotable(path) and before[0] == "str" and now == ("str", word.sub(ERASED, before[1]))
        )
    ]


def _holds_answers(path):
    return path[0] in OWNED or any(step in ("answers", "answers_json") for step in path)


def _cell(path, value, user, fields, kept, answers):
    if isinstance(value, str) and (path[-1].endswith("_json") or _container(value) is not None):
        parsed = json.loads(value)
        if user and path[-1] == "value_json" and isinstance(parsed, str):
            answers.append(parsed)
        else:
            _walk(path, parsed, fields, kept, answers)
    else:
        kept.append((path, (type(value).__name__, value)))


def _projection(path, request_id):
    kept, answers = [], []
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        (questions,) = db.execute(
            "SELECT answers_json FROM agentic_questions WHERE request_id=?", (request_id,)
        ).fetchone()
        fields = set(json.loads(questions))
        cells = []
        for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            names = [column[1] for column in db.execute(f'PRAGMA table_info("{table}")')]
            query = LINKED.get(table)
            if query is None and "request_id" in names:
                query = f'SELECT * FROM "{table}" WHERE request_id=? ORDER BY rowid'
            for index, row in enumerate(db.execute(query, (request_id,)) if query else []):
                user = table == "facts" and row["source"] == "user"
                for name in row.keys():
                    if (table, name) not in MOVED_COLUMNS:
                        cells.append(((table, index, name), row[name], user))
        for response_id, text in db.execute(RAW_PAYLOADS, (request_id,)):
            cells.append((("raw_payloads", response_id, "response_json"), text, False))
        for response_id, row_index, natural_key, text in db.execute(RAW_ROWS, (request_id,)):
            cells.append((("raw_rows", response_id, row_index, "natural_key"), natural_key, False))
            cells.append((("raw_rows", response_id, row_index, "raw_json"), text, False))
    for where, value, user in cells:
        _cell(where, value, user, fields, kept, answers)
    return kept, answers


def _confirmed_space(path, request_id):
    with closing(sqlite3.connect(path)) as db:
        return db.execute(CONFIRMED_SPACE, (request_id, CONFIRMED_UNIT)).fetchall()


def _answered_request(client, text, **space):
    waiting = client.post(
        "/api/v1/analyses?mock=true", json={"address": "시험", "allow_questions": True, **space}
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


def _record_get_facts(path, request_id):
    with closing(sqlite3.connect(path)) as db:
        snapshot_id, run_id, state = db.execute(
            "SELECT snapshot_id, run_id, state_json FROM agentic_runs WHERE request_id=?",
            (request_id,),
        ).fetchone()
        fact_ids = [
            fact_id
            for (fact_id,) in db.execute(
                "SELECT fact_id FROM facts WHERE request_id=? AND source='user'", (request_id,)
            )
        ]
    scope = CaptureScope(request_id, Path(path), run_id, snapshot_id)
    result = read_tools._facts(scope, GetFactsInput(fact_ids=fact_ids))
    reply = ToolReply(status="ok", data=result).model_dump_json()
    state = json.loads(state)
    state["messages"].append({"role": "tool", "tool_call_id": "call_facts", "content": reply})
    with closing(sqlite3.connect(path)) as db:
        db.execute(
            "INSERT INTO tool_calls(tool_call_id,request_id,snapshot_id,run_id,actor,tool_name,"
            "input_json,reply_json,created_at) VALUES(?,?,?,?,'decision','get_facts',?,?,?)",
            (
                "call_facts_" + request_id,
                request_id,
                snapshot_id,
                run_id,
                json.dumps({"fact_ids": fact_ids}),
                reply,
                "2026-11-08T00:00:00+00:00",
            ),
        )
        db.execute(
            "UPDATE agentic_runs SET state_json=? WHERE request_id=?",
            (json.dumps(state, ensure_ascii=False), request_id),
        )
        db.commit()


def _notes(found):
    return [e["detail"] for e in found["/events"]["events"] if e["stage"] == "note"]


def _run_script(path, request_id):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path), request_id],
        cwd=BACKEND,
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=60,
    )


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
            cls.number_id = _answered_request(client, "1")
            cls.token_id = _answered_request(client, "floor")
            cls.verdict_id = _answered_request(client, VERDICT)
            cls.shared_ids = [_answered_request(client, SHARED) for _ in range(2)]
            cls.short_id = _answered_request(client, SHORT)
            cls.phone_id = _answered_request(client, PHONE)
            cls.food_id = _answered_request(client, FOOD)
            cls.space_id = _answered_request(client, SPACE_ANSWER, **SPACE)
        _add_event(cls.template, cls.request_id, json.dumps({"note": SENTINEL}))
        _add_event(cls.template, cls.phone_id, json.dumps(PHONE_NOTE, ensure_ascii=False))
        _add_event(cls.template, cls.food_id, json.dumps(FOOD_NOTE, ensure_ascii=False))
        for request_id in (cls.short_id, cls.phone_id):
            _record_get_facts(cls.template, request_id)

    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "answers.sqlite3"
        with (
            closing(sqlite3.connect(self.template)) as source,
            closing(sqlite3.connect(self.path)) as target,
        ):
            source.backup(target)

    def client(self):
        app = create_app(settings=ExecutionSettings(db_path=self.path), load_env=False)
        login(app, self.path)
        return self.enterContext(TestClient(app))

    def read(self, request_id):
        client = self.client()
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

    def test_numbers_keys_and_enum_values_stay_byte_identical(self):
        cases = (
            (self.number_id, "1"),
            (self.token_id, "floor"),
            (self.verdict_id, VERDICT),
            (self.food_id, FOOD),
        )
        for request_id, answer in cases:
            with self.subTest(answer=answer):
                kept, answers = _projection(self.path, request_id)
                self.assertEqual(set(answers), {answer})
                self.assertGreater(erasure.erase_user_answers(request_id, db_path=self.path), 0)
                after_kept, after_answers = _projection(self.path, request_id)
                self.assertEqual([path for path, _ in after_kept], [path for path, _ in kept])
                self.assertEqual(_bad_changes(kept, after_kept, answer), [])
                self.assertEqual(after_answers, [ERASED] * len(answers))
                self.read(request_id)
        enums = [value for _, value in _projection(self.path, self.verdict_id)[0]]
        self.assertIn(("str", VERDICT), enums)

    def test_confirmed_floor_and_area_are_kept(self):
        before = _confirmed_space(self.path, self.space_id)
        self.assertEqual(len(before), 2)
        self.assertGreater(erasure.erase_user_answers(self.space_id, db_path=self.path), 0)
        self.assertEqual(_confirmed_space(self.path, self.space_id), before)
        self.assertEqual(_hits(self.path, SPACE_ANSWER), 0)
        facts = self.read(self.space_id)["/facts"]["facts"]
        self.assertEqual(
            {fact["metric"]: fact["value"] for fact in facts if fact["source"] == "user"},
            {"floor": "지하 1층", "exclusive_area": "84.5㎡", "existing_facilities": ERASED},
        )

    def test_korean_answer_is_not_cut_out_of_words_or_labels(self):
        erasure.erase_user_answers(self.food_id, db_path=self.path)
        found = self.read(self.food_id)
        self.assertEqual(_notes(found), [FOOD_NOTE | {"summary": "주변에 [삭제됨]이 많아요"}])

    def test_answers_copied_by_ai_tools_are_erased(self):
        expected = {SHORT: [], PHONE: [{"note": "연락처 [삭제됨] 로 연락"}]}
        for request_id, answer in ((self.short_id, SHORT), (self.phone_id, PHONE)):
            with self.subTest(answer=answer):
                with closing(sqlite3.connect(self.path)) as db:
                    (reply,) = db.execute(
                        "SELECT reply_json FROM tool_calls WHERE request_id=? "
                        "AND tool_name='get_facts'",
                        (request_id,),
                    ).fetchone()
                self.assertIn(answer, reply)
                self.assertGreater(erasure.erase_user_answers(request_id, db_path=self.path), 0)
                self.assertEqual(_hits(self.path, answer, request_id), 0)
                self.assertEqual(_notes(self.read(request_id)), expected[answer])

    def test_number_glued_to_korean_word_is_erased(self):
        _add_event(self.path, self.phone_id, json.dumps({"note": f"전화{PHONE}로 연락"}))
        erasure.erase_user_answers(self.phone_id, db_path=self.path)
        self.assertEqual(
            _notes(self.read(self.phone_id)),
            [{"note": "연락처 [삭제됨] 로 연락"}, {"note": "전화[삭제됨]로 연락"}],
        )

    def test_shared_raw_payload_is_copied_not_changed(self):
        erased, other = self.shared_ids
        self.assertEqual(_evidence(self.path, other), [(SHARED, SHARED)])
        erasure.erase_user_answers(erased, db_path=self.path)
        self.assertEqual(_hits(self.path, SHARED, erased), 0)
        self.assertGreater(_hits(self.path, SHARED, other), 0)
        self.assertEqual(_evidence(self.path, erased), [(ERASED, ERASED)])
        self.assertEqual(_evidence(self.path, other), [(SHARED, SHARED)])
        self.assertEqual(_wrong_content_hashes(self.path), [])
        later = _answered_request(self.client(), SHARED)
        self.assertEqual(_evidence(self.path, later), [(SHARED, SHARED)])
        self.assertEqual(_wrong_content_hashes(self.path), [])
        self.read(erased)

    def test_unshared_original_payload_is_removed(self):
        user_payload = "SELECT payload_hash FROM raw_responses WHERE request_id=? AND source='user'"
        with closing(sqlite3.connect(self.path)) as db:
            (old,) = db.execute(user_payload, (self.request_id,)).fetchone()
        erasure.erase_user_answers(self.request_id, db_path=self.path)
        with closing(sqlite3.connect(self.path)) as db:
            (new,) = db.execute(user_payload, (self.request_id,)).fetchone()
            stored = dict(
                db.execute(
                    "SELECT payload_hash, response_json FROM raw_payloads "
                    "WHERE payload_hash IN (?, ?)",
                    (old, new),
                ).fetchall()
            )
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertNotEqual(new, old)
        self.assertEqual(list(stored), [new])
        self.assertEqual(canonical_hash(json.loads(stored[new])), new)

    def test_unfinished_request_is_refused(self):
        before, hits = _triggers(self.path), _hits(self.path, SENTINEL)
        for status in ("pending", "running", "waiting_for_input"):
            with self.subTest(status=status):
                with closing(sqlite3.connect(self.path)) as db:
                    db.execute(
                        "UPDATE analysis_requests SET status=?, completed_at=NULL, "
                        "result_json=NULL WHERE request_id=?",
                        (status, self.request_id),
                    )
                    db.commit()
                with self.assertRaisesRegex(AnalysisConflictError, REFUSED):
                    erasure.erase_user_answers(self.request_id, db_path=self.path)
                result = _run_script(self.path, self.request_id)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn(REFUSED, result.stderr)
                self.assertEqual(_hits(self.path, SENTINEL), hits)
                self.assertEqual(_triggers(self.path), before)

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
            result = _run_script(self.path, request_id)
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
