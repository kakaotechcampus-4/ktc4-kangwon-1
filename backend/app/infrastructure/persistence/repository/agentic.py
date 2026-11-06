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
    db.execute(
        "INSERT INTO tool_calls(tool_call_id,request_id,snapshot_id,run_id,actor,"
        "tool_name,input_json,reply_json,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        values,
    )


def advisor_consult_ids(db, request_id, snapshot_id):
    return db.execute(
        "SELECT consult_id FROM advisor_consults WHERE request_id=? AND snapshot_id=?",
        (request_id, snapshot_id),
    ).fetchall()


def insert_report(db, values):
    db.execute(
        "INSERT INTO agentic_reports(report_id,request_id,snapshot_id,"
        "proposal_json,result_json,rendered_json,phase,created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        values,
    )


def save_run(db, values):
    db.execute(
        "INSERT INTO agentic_runs(request_id,snapshot_id,run_id,status,state_json,"
        "result_json,updated_at) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT(request_id) DO UPDATE SET "
        "status=excluded.status,state_json=excluded.state_json,"
        "result_json=excluded.result_json,updated_at=excluded.updated_at",
        values,
    )


def run_state(db, request_id, snapshot_id):
    return db.execute(
        "SELECT state_json,status FROM agentic_runs WHERE request_id=? AND snapshot_id=?",
        (request_id, snapshot_id),
    ).fetchone()


def resume_run(db, request_id, snapshot_id, state_json):
    db.execute(
        "UPDATE agentic_runs SET status='running',state_json=? "
        "WHERE request_id=? AND snapshot_id=?",
        (state_json, request_id, snapshot_id),
    )


def resume_request(db, request_id):
    db.execute(
        "UPDATE analysis_requests SET status='running' WHERE request_id=? "
        "AND status='waiting_for_input'",
        (request_id,),
    )


def insert_question(db, values):
    db.execute(
        "INSERT INTO agentic_questions(question_session_id,request_id,snapshot_id,"
        "questions_json,answers_json,status,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        values,
    )


def question_session(db, request_id, snapshot_id):
    return db.execute(
        "SELECT question_session_id,questions_json,status FROM "
        "agentic_questions WHERE request_id=? AND snapshot_id=?",
        (request_id, snapshot_id),
    ).fetchone()


def question_status(db, question_session_id):
    return db.execute(
        "SELECT status FROM agentic_questions WHERE question_session_id=?",
        (question_session_id,),
    ).fetchone()


def mark_question_answered(db, question_session_id, answers_json):
    db.execute(
        "UPDATE agentic_questions SET status='answered',answers_json=? WHERE question_session_id=?",
        (answers_json, question_session_id),
    )


def replace_ask_user_reply(db, request_id, snapshot_id, question_session_id, reply_json):
    db.execute(
        "UPDATE tool_calls SET reply_json=? WHERE request_id=? AND snapshot_id=? "
        "AND tool_name='ask_user' AND json_extract(reply_json,'$.data.question_session_id')=?",
        (reply_json, request_id, snapshot_id, question_session_id),
    )


def finalize_report(db, report_id, result_json):
    db.execute(
        "UPDATE agentic_reports SET result_json=?,phase='final' WHERE report_id=?",
        (result_json, report_id),
    )


def insert_review(db, values):
    db.execute(
        "INSERT INTO agentic_reviews(request_id,snapshot_id,actor,review_json,"
        "created_at) "
        "VALUES(?,?,?,?,?)",
        values,
    )


def insert_advisor_consult(db, values):
    db.execute(
        "INSERT INTO advisor_consults(consult_id,request_id,snapshot_id,question,"
        "fact_ids_json,model,family,usage_json,answer_json,status,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        values,
    )
