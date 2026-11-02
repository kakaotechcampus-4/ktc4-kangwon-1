"""코드 점수 스냅샷과 문항 점수를 읽고 씁니다."""


def snapshot_summary_json(db, score_snapshot_id):
    row = db.execute(
        "SELECT summary_json FROM score_snapshots WHERE score_snapshot_id=?",
        (score_snapshot_id,),
    ).fetchone()
    return None if row is None else row[0]


def scoped_snapshot_summary(db, score_snapshot_id, request_id, snapshot_id):
    return db.execute(
        "SELECT summary_json FROM score_snapshots WHERE score_snapshot_id=? "
        "AND request_id=? AND snapshot_id=?",
        (score_snapshot_id, request_id, snapshot_id),
    ).fetchone()


def item_fact_ids(db, score_snapshot_id):
    return db.execute(
        "SELECT industry_code,item,fact_ids_json FROM scores WHERE score_snapshot_id=?",
        (score_snapshot_id,),
    ).fetchall()


def insert_score_snapshot(db, values):
    db.execute("INSERT INTO score_snapshots VALUES(?,?,?,?,?,?,?,?,?,?)", values)


def insert_score(db, values):
    db.execute("INSERT INTO scores VALUES(?,?,?,?,?,?,?,?)", values)


def first_score_snapshot(db, request_id, snapshot_id):
    return db.execute(
        "SELECT score_snapshot_id,summary_json FROM score_snapshots WHERE "
        "request_id=? AND snapshot_id=? ORDER BY created_at LIMIT 1",
        (request_id, snapshot_id),
    ).fetchone()


def latest_score_snapshot(db, request_id, snapshot_id):
    return db.execute(
        "SELECT score_snapshot_id,summary_json FROM score_snapshots "
        "WHERE request_id=? AND snapshot_id=? ORDER BY created_at DESC LIMIT 1",
        (request_id, snapshot_id),
    ).fetchone()


def code_item_fact_ids(db, score_snapshot_id):
    return db.execute(
        "SELECT fact_ids_json FROM scores WHERE score_snapshot_id=? AND item!='L'",
        (score_snapshot_id,),
    ).fetchall()


def item_fact_ids_json(db, score_snapshot_id, industry_code, item):
    return db.execute(
        "SELECT fact_ids_json FROM scores WHERE score_snapshot_id=? AND industry_code=? AND item=?",
        (score_snapshot_id, industry_code, item),
    ).fetchone()[0]


def industry_scores(db, score_snapshot_id, industry_code):
    return db.execute(
        "SELECT item,status,grade,points,fact_ids_json FROM scores "
        "WHERE score_snapshot_id=? AND industry_code=?",
        (score_snapshot_id, industry_code),
    ).fetchall()


def scores_for_industries(db, score_snapshot_id, codes):
    return db.execute(
        "SELECT industry_code,item,status,grade,points,fact_ids_json FROM scores "
        "WHERE score_snapshot_id=? AND industry_code IN (" + ",".join("?" for _ in codes) + ")",
        [score_snapshot_id, *codes],
    ).fetchall()
