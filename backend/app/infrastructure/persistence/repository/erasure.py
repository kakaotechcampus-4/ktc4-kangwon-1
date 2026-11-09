import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.application.errors import AnalysisConflictError
from app.domain.facts import ANSWER_UNIT
from app.infrastructure.persistence.connection import connect
from app.infrastructure.persistence.repository.common import _dumps, _text, begin_immediate
from app.shared.canonical import canonical_hash, canonical_json

_ERASED = "[삭제됨]"
_UNFINISHED = frozenset({"pending", "running", "waiting_for_input"})
_ESCAPE_DEPTH = 2
_QUOTE_MIN_LENGTH = 3
_PLAIN_QUOTE_MIN_LENGTH = 8
_WHOLE_VALUE_MIN_LENGTH = 12
_PAYLOADS = "raw_payloads"
_ROWS = "raw_rows"
_FACTS = "facts"
_ANSWER_KEYS = frozenset({"answers", "answers_json"})
_PROSE_COLUMNS = frozenset({"question"})
_FIXED_KEY = re.compile(
    r"(?:^|_)(?:id|ids|at|hash|key|code|codes|status|source|metric|field|unit|period|kind|"
    r"type|stage|event|actor|role|phase|method|version|name|names|pointer)$"
    r"|category|[a-z0-9](?:Nm|Cd)$"
)
_JSON_CHECK = re.compile(r'json_valid\(\s*"?(\w+)"?\s*\)')
_WORD = re.compile(r"[0-9A-Za-z_]")
_LETTER = re.compile(r"[가-힣0-9A-Za-z_]")


@dataclass(frozen=True)
class _Rule:
    answers: dict[str, frozenset[str]]
    texts: frozenset[str]
    quotes: tuple[re.Pattern[str], ...]
    needles: tuple[str, ...]
    facts: frozenset[str]


@dataclass(frozen=True)
class _Origin:
    answers: bool
    prose: bool


_RECORD = _Origin(answers=False, prose=True)
_DATA = _Origin(answers=False, prose=False)
_USER = _Origin(answers=True, prose=False)


def erase_user_answers(request_id: str, *, db_path: str | Path | None = None) -> int:
    request_id = _text(request_id)
    with connect(db_path) as db:
        begin_immediate(db)
        rule = _rule(db, request_id)
        if rule is None:
            return 0
        start = db.total_changes
        tables = _tables(db)
        links = _links(db, tables)
        scopes = _scopes(db, tables, links)
        changes = _changes(db, request_id, scopes, rule)
        payloads = _changed_payloads(db, rule)
        triggers = _triggers(db, _touched(changes, payloads, links))
        for name, _ in triggers:
            db.execute(f'DROP TRIGGER "{name}"')
        for table, rowid, values in changes:
            _rewrite(db, table, rowid, values)
        _split_payloads(db, request_id, scopes, links, payloads, rule)
        for _, sql in triggers:
            db.execute(sql)
        return db.total_changes - start


def _rule(db, request_id):
    row = db.execute(
        "SELECT status FROM analysis_requests WHERE request_id=?", (request_id,)
    ).fetchone()
    if row is None:
        return None
    pairs = [
        (field, value)
        for (text,) in db.execute(
            "SELECT answers_json FROM agentic_questions WHERE request_id=?", (request_id,)
        ).fetchall()
        for field, value in json.loads(text).items()
        if isinstance(value, str) and value.strip()
    ]
    if not pairs:
        return None
    if row["status"] in _UNFINISHED:
        raise AnalysisConflictError("분석이 끝난 뒤에 지울 수 있습니다.")
    facts = frozenset(
        fact_id
        for (fact_id,) in db.execute(
            "SELECT fact_id FROM facts WHERE request_id=? AND source='user' AND unit=?",
            (request_id, ANSWER_UNIT),
        ).fetchall()
    )
    answers = {}
    for field, value in pairs:
        answers.setdefault(field, set()).add(value)
    texts = frozenset(value for _, value in pairs)
    quotes = tuple(
        _quote(text)
        for text in sorted(texts, key=lambda text: (-len(text), text))
        if len(text) >= _PLAIN_QUOTE_MIN_LENGTH
        or (len(text) >= _QUOTE_MIN_LENGTH and any(char.isalpha() for char in text))
    )
    frozen = {field: frozenset(values) for field, values in answers.items()}
    return _Rule(frozen, texts, quotes, _needles(texts), facts)


def _quote(text):
    head = ""
    if _LETTER.fullmatch(text[0]):
        joined = _WORD if text[0].isdigit() else _LETTER
        head = f"(?<!{joined.pattern})"
    tail = f"(?!{_WORD.pattern})" if _WORD.fullmatch(text[-1]) else ""
    return re.compile(head + re.escape(text) + tail)


def _needles(texts):
    found = set(texts)
    for _ in range(_ESCAPE_DEPTH):
        found |= {
            json.dumps(form, ensure_ascii=ascii)[1:-1] for form in found for ascii in (False, True)
        }
    return tuple(sorted(found))


def _tables(db):
    return [
        name
        for (name,) in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]


def _column_names(db, table):
    return [column["name"] for column in db.execute(f'PRAGMA table_info("{table}")').fetchall()]


def _links(db, tables):
    return [
        (table, link["from"], link["table"], link["to"])
        for table in tables
        for link in db.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
        if link["to"] and link["table"] != table
    ]


def _scopes(db, tables, links):
    scopes = {
        table: '"request_id"=:request_id'
        for table in tables
        if "request_id" in _column_names(db, table)
    }
    while grown := _grow(scopes, links):
        scopes |= grown
    return scopes


def _grow(scopes, links):
    found = {}
    for child, column, parent, key in links:
        if child not in scopes and parent in scopes:
            found.setdefault(child, []).append(_within(column, parent, key, scopes))
    for parent in {link[2] for link in links} - scopes.keys() - found.keys():
        children = [link for link in links if link[2] == parent]
        if all(child in scopes for child, _, _, _ in children):
            found[parent] = [
                _within(key, child, column, scopes) for child, column, _, key in children
            ]
    return {table: " OR ".join(conditions) for table, conditions in found.items()}


def _within(column, table, other, scopes):
    return f'"{column}" IN (SELECT "{other}" FROM "{table}" WHERE {scopes[table]})'


def _erasable_columns(db, table):
    (sql,) = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    checked = set(_JSON_CHECK.findall(sql))
    keys = {link["from"] for link in db.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()}
    columns = {}
    for column in db.execute(f'PRAGMA table_info("{table}")').fetchall():
        name = column["name"]
        if "TEXT" not in column["type"].upper() or column["pk"] or name in keys:
            continue
        if name.endswith("_json") or name in checked:
            columns[name] = True
        elif name in _PROSE_COLUMNS:
            columns[name] = False
    return columns


def _changes(db, request_id, scopes, rule):
    needles = {f"needle{index}": needle for index, needle in enumerate(rule.needles)}
    changes = []
    for table, scope in scopes.items():
        columns = {} if table in (_PAYLOADS, _ROWS) else _erasable_columns(db, table)
        if not columns:
            continue
        keyed = table == _FACTS
        names = [*columns, *(["fact_id"] if keyed else [])]
        selected = ",".join(f'"{name}"' for name in names)
        match = " OR ".join(
            f'instr("{column}",:{name})>0' for column in columns for name in needles
        )
        rows = db.execute(
            f'SELECT rowid,{selected} FROM "{table}" WHERE ({scope}) AND ({match})',
            {"request_id": request_id, **needles},
        ).fetchall()
        default = _DATA if "source" in _column_names(db, table) else _RECORD
        for row in rows:
            origin = _USER if keyed and row["fact_id"] in rule.facts else default
            values = _row_values(row, columns, rule, origin)
            if values:
                changes.append((table, row[0], values))
    return changes


def _row_values(row, columns, rule, origin):
    values = {}
    for column, is_json in columns.items():
        old = row[column]
        if not isinstance(old, str):
            continue
        if is_json:
            new = _erase_cell(old, rule, column, origin)
        else:
            new = _erase_string(old, rule, key=column, inside=False, prose=origin.prose)
        if new != old:
            values[column] = new
    return values


def _erase_cell(text, rule, column, origin):
    try:
        value = json.loads(text)
    except ValueError:
        return _erase_string(text, rule, key=column, inside=False, prose=origin.prose)
    if origin.answers and isinstance(value, str):
        erased = _erase_answer(value, rule)
    else:
        inside = origin.answers or column in _ANSWER_KEYS
        erased = _erase_value(value, rule, key=column, inside=inside, prose=origin.prose)
    return text if erased == value else _dumps(erased)


def _erase_value(value, rule, *, inside, prose, key=None):
    if isinstance(value, dict | list) and _fixed(key):
        return value
    if isinstance(value, dict):
        user = value.get("source") == "user" and value.get("fact_id") in rule.facts
        return {
            name: _erase_answer(item, rule)
            if user and name == "value"
            else _erase_value(
                item, rule, key=name, inside=inside or name in _ANSWER_KEYS, prose=prose
            )
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [_erase_value(item, rule, key=key, inside=inside, prose=prose) for item in value]
    if isinstance(value, str):
        return _erase_string(value, rule, key=key, inside=inside, prose=prose)
    return value


def _erase_answer(value, rule):
    if isinstance(value, dict):
        return {name: _erase_answer(item, rule) for name, item in value.items()}
    if isinstance(value, list):
        return [_erase_answer(item, rule) for item in value]
    return _ERASED if isinstance(value, str) and value in rule.texts else value


def _erase_string(value, rule, *, key, inside, prose):
    if inside and value in rule.answers.get(key, ()):
        return _ERASED
    if _fixed(key):
        return value
    nested = _container(value)
    if nested is not None:
        erased = _erase_value(nested, rule, inside=False, prose=prose)
        return value if erased == nested else _dumps(erased)
    if not prose:
        return value
    if value in rule.texts:
        return _ERASED if len(value) >= _WHOLE_VALUE_MIN_LENGTH else value
    for quote in rule.quotes:
        value = quote.sub(_ERASED, value)
    return value


def _fixed(key):
    return key is not None and _FIXED_KEY.search(key) is not None


def _container(value):
    if not value.lstrip().startswith(("{", "[")):
        return None
    try:
        parsed = json.loads(value)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict | list) else None


def _changed_payloads(db, rule):
    found = {}
    marks = ",".join("?" for _ in rule.facts)
    for payload_hash, text in db.execute(
        "SELECT DISTINCT b.payload_hash,b.response_json FROM fact_sources s "
        "JOIN raw_rows r USING(raw_row_id) JOIN raw_payloads b USING(payload_hash) "
        f"WHERE s.fact_id IN ({marks})",
        sorted(rule.facts),
    ).fetchall():
        if not any(needle in text for needle in rule.needles):
            continue
        value = json.loads(text)
        erased = _erase_value(value, rule, inside=True, prose=False)
        if erased != value:
            found[payload_hash] = erased
    return found


def _touched(changes, payloads, links):
    touched = {table for table, _, _ in changes}
    if payloads:
        moved = {_PAYLOADS, _ROWS}
        touched |= moved | {child for child, _, parent, _ in links if parent in moved}
    return touched


def _triggers(db, tables):
    if not tables:
        return []
    marks = ",".join("?" for _ in tables)
    return db.execute(
        f"SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name IN ({marks}) "
        "ORDER BY name",
        sorted(tables),
    ).fetchall()


def _rewrite(db, table, rowid, values):
    assignments = ",".join(f'"{column}"=?' for column in values)
    db.execute(f'UPDATE "{table}" SET {assignments} WHERE rowid=?', [*values.values(), rowid])


def _split_payloads(db, request_id, scopes, links, payloads, rule):
    if not payloads:
        return
    moved = {}
    for old, erased in payloads.items():
        new = canonical_hash(erased)
        db.execute(
            "INSERT OR IGNORE INTO raw_payloads(payload_hash,response_json) VALUES(?,?)",
            (new, canonical_json(erased)),
        )
        for row in db.execute(
            "SELECT * FROM raw_rows WHERE payload_hash=? ORDER BY row_index", (old,)
        ).fetchall():
            moved[row["raw_row_id"]] = _copied_row(db, row, new, rule)
        _repoint(db, request_id, scopes, links, _PAYLOADS, {old: new})
    _repoint(db, request_id, scopes, links, _ROWS, moved)
    _delete_unreferenced(db, links, _ROWS, "raw_row_id", moved)
    _delete_unreferenced(db, links, _PAYLOADS, "payload_hash", payloads)


def _copied_row(db, row, payload_hash, rule):
    found = db.execute(
        "SELECT raw_row_id FROM raw_rows WHERE payload_hash=? AND row_index=?",
        (payload_hash, row["row_index"]),
    ).fetchone()
    if found is not None:
        return found[0]
    value = _erase_value(json.loads(row["raw_json"]), rule, inside=True, prose=False)
    raw_row_id = "rr_" + str(uuid.uuid4())
    db.execute(
        "INSERT INTO raw_rows(raw_row_id,payload_hash,row_index,natural_key,raw_json,row_hash) "
        "VALUES(?,?,?,?,?,?)",
        (
            raw_row_id,
            payload_hash,
            row["row_index"],
            row["natural_key"],
            canonical_json(value),
            canonical_hash(value),
        ),
    )
    return raw_row_id


def _repoint(db, request_id, scopes, links, parent, moved):
    for child, column, target, _ in links:
        if target != parent or child == _ROWS or child not in scopes:
            continue
        for old, new in moved.items():
            db.execute(
                f'UPDATE "{child}" SET "{column}"=:new WHERE "{column}"=:old AND ({scopes[child]})',
                {"new": new, "old": old, "request_id": request_id},
            )


def _delete_unreferenced(db, links, table, key, values):
    referrers = [(child, column) for child, column, parent, _ in links if parent == table]
    for value in values:
        if not any(
            db.execute(f'SELECT 1 FROM "{child}" WHERE "{column}"=? LIMIT 1', (value,)).fetchone()
            for child, column in referrers
        ):
            db.execute(f'DELETE FROM "{table}" WHERE "{key}"=?', (value,))
