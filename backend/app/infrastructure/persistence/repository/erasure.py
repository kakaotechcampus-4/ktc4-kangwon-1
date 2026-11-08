import json
from pathlib import Path

from app.infrastructure.persistence.connection import connect
from app.infrastructure.persistence.repository.common import _text, begin_immediate

_ERASED = "[삭제됨]"
_ESCAPE_DEPTH = 2


def erase_user_answers(request_id: str, *, db_path: str | Path | None = None) -> int:
    request_id = _text(request_id)
    with connect(db_path) as db:
        begin_immediate(db)
        pairs = _replacements(_answer_texts(db, request_id))
        changes = _changes(db, request_id, pairs) if pairs else []
        if not changes:
            return 0
        triggers = _triggers(db, {table for table, _, _ in changes})
        for name, _ in triggers:
            db.execute(f'DROP TRIGGER "{name}"')
        for table, rowid, values in changes:
            _rewrite(db, table, rowid, values)
        for _, sql in triggers:
            db.execute(sql)
    return len(changes)


def _answer_texts(db, request_id):
    values = [
        value
        for (answers,) in db.execute(
            "SELECT answers_json FROM agentic_questions WHERE request_id=?", (request_id,)
        ).fetchall()
        for value in json.loads(answers).values()
    ]
    values += [
        json.loads(value)
        for (value,) in db.execute(
            "SELECT value_json FROM facts WHERE request_id=? AND source='user'", (request_id,)
        ).fetchall()
    ]
    return {value for value in values if isinstance(value, str) and value.strip()}


def _escaped(text, ascii):
    return json.dumps(text, ensure_ascii=ascii)[1:-1]


def _forms(text):
    forms = {text: _ERASED}
    for _ in range(_ESCAPE_DEPTH):
        for form, erased in list(forms.items()):
            for ascii in (False, True):
                forms.setdefault(_escaped(form, ascii), _escaped(erased, ascii))
    return forms


def _replacements(texts):
    pairs = {}
    for text in sorted(texts):
        for form, erased in _forms(text).items():
            pairs.setdefault(form, erased)
    return sorted(pairs.items(), key=lambda pair: (-len(pair[0]), pair[0]))


def _scopes(db):
    tables = [
        name
        for (name,) in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    links = [
        (table, link["from"], link["table"], link["to"])
        for table in tables
        for link in db.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
        if link["to"] and link["table"] != table
    ]
    scopes = {
        table: '"request_id"=:request_id'
        for table in tables
        if any(
            column["name"] == "request_id"
            for column in db.execute(f'PRAGMA table_info("{table}")').fetchall()
        )
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


def _text_columns(db, table):
    keys = {link["from"] for link in db.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()}
    return [
        column["name"]
        for column in db.execute(f'PRAGMA table_info("{table}")').fetchall()
        if "TEXT" in column["type"].upper() and not column["pk"] and column["name"] not in keys
    ]


def _changes(db, request_id, pairs):
    forms = {f"form{index}": form for index, (form, _) in enumerate(pairs)}
    changes = []
    for table, scope in _scopes(db).items():
        columns = _text_columns(db, table)
        if not columns:
            continue
        match = " OR ".join(f'instr("{column}",:{name})>0' for column in columns for name in forms)
        selected = ",".join(f'"{column}"' for column in columns)
        rows = db.execute(
            f'SELECT rowid,{selected} FROM "{table}" WHERE ({scope}) AND ({match})',
            {"request_id": request_id, **forms},
        ).fetchall()
        for row in rows:
            values = {
                column: _erase(row[column], pairs)
                for column in columns
                if isinstance(row[column], str)
            }
            values = {column: value for column, value in values.items() if value != row[column]}
            if values:
                changes.append((table, row[0], values))
    return changes


def _erase(value, pairs):
    for form, erased in pairs:
        value = value.replace(form, erased)
    return value


def _triggers(db, tables):
    marks = ",".join("?" for _ in tables)
    return db.execute(
        f"SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name IN ({marks}) "
        "ORDER BY name",
        sorted(tables),
    ).fetchall()


def _rewrite(db, table, rowid, values):
    assignments = ",".join(f'"{column}"=?' for column in values)
    db.execute(f'UPDATE "{table}" SET {assignments} WHERE rowid=?', [*values.values(), rowid])
