"""코드 점수 스냅샷과 문항 점수를 읽고 씁니다."""

import json

from app.application.ports.records import ItemScore, ScoreSnapshot


def score_rows(db, score_snapshot_id):
    row = db.execute(
        "SELECT summary_json FROM score_snapshots WHERE score_snapshot_id=?",
        (score_snapshot_id,),
    ).fetchone()
    return None if row is None else json.loads(row[0])


def scoped_score_rows(db, score_snapshot_id, request_id, snapshot_id):
    row = db.execute(
        "SELECT summary_json FROM score_snapshots WHERE score_snapshot_id=? "
        "AND request_id=? AND snapshot_id=?",
        (score_snapshot_id, request_id, snapshot_id),
    ).fetchone()
    return None if row is None else json.loads(row[0])


def item_fact_ids(db, score_snapshot_id):
    return {
        (row[0], row[1]): json.loads(row[2])
        for row in db.execute(
            "SELECT industry_code,item,fact_ids_json FROM scores WHERE score_snapshot_id=?",
            (score_snapshot_id,),
        ).fetchall()
    }


def insert_score_snapshot(
    db,
    *,
    score_snapshot_id,
    request_id,
    snapshot_id,
    run_id,
    rubric_version,
    calc_version,
    summary_text,
    top5_text,
    review_state,
    created_at,
):
    db.execute(
        "INSERT INTO score_snapshots(score_snapshot_id,request_id,snapshot_id,"
        "run_id,rubric_version,calc_version,summary_json,top5_json,L_review_state,"
        "created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            score_snapshot_id,
            request_id,
            snapshot_id,
            run_id,
            rubric_version,
            calc_version,
            summary_text,
            top5_text,
            review_state,
            created_at,
        ),
    )


def insert_score(
    db, *, score_snapshot_id, industry_code, item, weight, status, grade, points, fact_ids_text
):
    db.execute(
        "INSERT INTO scores(score_snapshot_id,industry_code,item,weight,status,"
        "grade,points,fact_ids_json) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (score_snapshot_id, industry_code, item, weight, status, grade, points, fact_ids_text),
    )


def first_score_snapshot(db, request_id, snapshot_id):
    row = db.execute(
        "SELECT score_snapshot_id,summary_json FROM score_snapshots WHERE "
        "request_id=? AND snapshot_id=? ORDER BY created_at LIMIT 1",
        (request_id, snapshot_id),
    ).fetchone()
    return None if row is None else ScoreSnapshot(row[0], json.loads(row[1]))


def latest_score_snapshot(db, request_id, snapshot_id):
    row = db.execute(
        "SELECT score_snapshot_id,summary_json FROM score_snapshots "
        "WHERE request_id=? AND snapshot_id=? ORDER BY created_at DESC LIMIT 1",
        (request_id, snapshot_id),
    ).fetchone()
    return None if row is None else ScoreSnapshot(row[0], json.loads(row[1]))


def code_item_fact_ids(db, score_snapshot_id):
    return {
        fact_id
        for row in db.execute(
            "SELECT fact_ids_json FROM scores WHERE score_snapshot_id=? AND item!='L'",
            (score_snapshot_id,),
        ).fetchall()
        for fact_id in json.loads(row[0])
    }


def fact_ids_of_item(db, score_snapshot_id, industry_code, item):
    row = db.execute(
        "SELECT fact_ids_json FROM scores WHERE score_snapshot_id=? AND industry_code=? AND item=?",
        (score_snapshot_id, industry_code, item),
    ).fetchone()
    return json.loads(row[0])


def industry_scores(db, score_snapshot_id, industry_code):
    return [
        ItemScore(industry_code, row[0], row[1], row[2], row[3], json.loads(row[4]))
        for row in db.execute(
            "SELECT item,status,grade,points,fact_ids_json FROM scores "
            "WHERE score_snapshot_id=? AND industry_code=?",
            (score_snapshot_id, industry_code),
        ).fetchall()
    ]


def scores_for_industries(db, score_snapshot_id, codes):
    return [
        ItemScore(row[0], row[1], row[2], row[3], row[4], json.loads(row[5]))
        for row in db.execute(
            "SELECT industry_code,item,status,grade,points,fact_ids_json FROM scores "
            "WHERE score_snapshot_id=? AND industry_code IN (" + ",".join("?" for _ in codes) + ")",
            [score_snapshot_id, *codes],
        ).fetchall()
    ]
