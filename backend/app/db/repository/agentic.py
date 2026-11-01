"""판단 루프의 실행 상태·질문·도구 기록·평가·리포트를 읽고 씁니다."""


def begin_immediate(db):
    if not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")


def decision_tool_calls(db, request_id, snapshot_id):
    return db.execute(
        "SELECT tool_call_id,reply_json FROM tool_calls WHERE request_id=? "
        "AND snapshot_id=? AND actor='decision'",
        (request_id, snapshot_id),
    ).fetchall()


def tool_call_history(db, request_id, snapshot_id, actor, tool_name):
    return db.execute(
        "SELECT input_json,reply_json FROM tool_calls WHERE request_id=? AND "
        "snapshot_id=? AND actor=? AND tool_name=? ORDER BY rowid",
        (request_id, snapshot_id, actor, tool_name),
    ).fetchall()


def insert_tool_call(db, values):
    db.execute("INSERT INTO tool_calls VALUES(?,?,?,?,?,?,?,?,?)", values)


def advisor_consult_ids(db, request_id, snapshot_id):
    return db.execute(
        "SELECT consult_id FROM advisor_consults WHERE request_id=? AND snapshot_id=?",
        (request_id, snapshot_id),
    ).fetchall()


def insert_report(db, values):
    db.execute("INSERT INTO agentic_reports VALUES(?,?,?,?,?,?,?,?)", values)
