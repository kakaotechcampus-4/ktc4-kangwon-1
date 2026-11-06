"""요청 스냅샷의 원문 응답·원문 행을 읽습니다."""


def raw_rows_in_scope(db, row_ids, request_id, snapshot_id):
    return {
        r[0]
        for r in db.execute(
            "SELECT DISTINCT e.raw_row_id FROM raw_response_rows e "
            "INDEXED BY raw_response_row_ref CROSS JOIN raw_responses p "
            "ON p.response_id=e.response_id WHERE e.raw_row_id IN ("
            + ",".join("?" for _ in row_ids)
            + ") AND p.request_id=? AND p.snapshot_id=?",
            [*row_ids, request_id, snapshot_id],
        )
    }


def response_in_scope(db, response_id, request_id, snapshot_id):
    return (
        db.execute(
            "SELECT 1 FROM raw_responses WHERE response_id=? AND request_id=? AND snapshot_id=?",
            (response_id, request_id, snapshot_id),
        ).fetchone()
        is not None
    )


def baseline_response_id(db, snapshot_id, file_hash):
    row = db.execute(
        "SELECT response_id FROM raw_responses WHERE snapshot_id=? AND "
        "source='baseline' AND json_extract(request_args_json,'$.file_hash')=?",
        (snapshot_id, file_hash),
    ).fetchone()
    return None if row is None else row[0]


def baseline_rows(db, snapshot_id):
    return db.execute(
        "SELECT r.raw_row_id,r.raw_json FROM raw_rows r "
        "JOIN raw_response_rows e USING(raw_row_id) JOIN raw_responses p "
        "USING(response_id) WHERE p.snapshot_id=? AND p.source='baseline' AND "
        "e.duplicate_of IS NULL",
        (snapshot_id,),
    ).fetchall()


def profile_response_id(db, request_id, snapshot_id, file_hash):
    row = db.execute(
        "SELECT response_id FROM raw_responses WHERE request_id=? AND snapshot_id=? "
        "AND source='industry_profile' AND json_extract(request_args_json,'$.file_hash')=?",
        (request_id, snapshot_id, file_hash),
    ).fetchone()
    return None if row is None else row[0]


def response_rows(db, response_id):
    return db.execute(
        "SELECT r.raw_row_id,r.raw_json FROM raw_rows r "
        "JOIN raw_response_rows e USING(raw_row_id) WHERE e.response_id=?",
        (response_id,),
    ).fetchall()


def first_row_id(db, response_id):
    return db.execute(
        "SELECT raw_row_id FROM raw_response_rows WHERE response_id=?", (response_id,)
    ).fetchone()[0]


def snapshot_responses(db, snapshot_id):
    return db.execute(
        "SELECT p.*,b.response_json FROM raw_responses p "
        "JOIN raw_payloads b USING(payload_hash) "
        "WHERE p.snapshot_id=? AND p.duplicate_of IS NULL",
        (snapshot_id,),
    ).fetchall()


def snapshot_rows(db, snapshot_id):
    return db.execute(
        "SELECT r.*,p.source,p.run_id,p.request_args_json,p.group_key FROM "
        "raw_rows r JOIN raw_response_rows e USING(raw_row_id) "
        "JOIN raw_responses p USING(response_id) WHERE p.snapshot_id=? "
        "AND p.duplicate_of IS NULL AND e.duplicate_of IS NULL",
        (snapshot_id,),
    ).fetchall()


def latest_regulation_rows(db, request_id, snapshot_id):
    return db.execute(
        "SELECT r.raw_json FROM raw_rows r JOIN raw_response_rows e USING(raw_row_id) "
        "JOIN raw_responses p USING(response_id) "
        "WHERE p.request_id=? AND p.snapshot_id=? AND p.source='regulation' "
        "ORDER BY p.collected_at DESC LIMIT 1",
        (request_id, snapshot_id),
    ).fetchall()


def map_row_ids(db, request_id, snapshot_id):
    return db.execute(
        "SELECT DISTINCT r.raw_row_id FROM raw_response_rows r "
        "JOIN raw_responses p USING(response_id) WHERE p.request_id=? "
        "AND p.snapshot_id=? AND p.source='map'",
        (request_id, snapshot_id),
    ).fetchall()


def raw_row_with_source(db, raw_row_id, request_id, snapshot_id):
    return db.execute(
        "SELECT r.raw_json,p.source FROM raw_rows r "
        "JOIN raw_response_rows e USING(raw_row_id) "
        "JOIN raw_responses p USING(response_id) "
        "WHERE r.raw_row_id=? AND p.request_id=? AND p.snapshot_id=?",
        (raw_row_id, request_id, snapshot_id),
    ).fetchone()
