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
