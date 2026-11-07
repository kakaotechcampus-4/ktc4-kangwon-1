"""fact·별칭·공간 비교 포인터를 읽고 씁니다."""

import sqlite3
from hashlib import sha256

from app.infrastructure.persistence.repository.agentic import begin_immediate


def fact_scope_row(db, fact_id, request_id, snapshot_id):
    return db.execute(
        "SELECT industry_code,status,citable FROM facts WHERE fact_id=? "
        "AND request_id=? AND snapshot_id=?",
        (fact_id, request_id, snapshot_id),
    ).fetchone()


def fact_id_by_identity(db, snapshot_id, identity_hash):
    row = db.execute(
        "SELECT fact_id FROM facts WHERE snapshot_id=? AND identity_hash=?",
        (snapshot_id, identity_hash),
    ).fetchone()
    return None if row is None else row[0]


def insert_fact(db, values):
    db.execute(
        "INSERT INTO facts(fact_id,request_id,snapshot_id,industry_code,source,"
        "metric,value_json,unit,period,spatial_scope_json,comparison_json,status,"
        "citable,calc_version,lineage_hash,identity_hash,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        values,
    )


def insert_local_fact_lineage(db, fact_id, ref, row_key, column):
    db.execute(
        "INSERT INTO local_fact_lineage(fact_id,provenance_id,row_key,column_name) VALUES(?,?,?,?)",
        (fact_id, ref, row_key, column),
    )


def insert_fact_sources(db, rows):
    db.executemany("INSERT INTO fact_sources(fact_id,raw_row_id,field_pointer) VALUES(?,?,?)", rows)


def insert_fact_parents(db, rows):
    db.executemany("INSERT INTO fact_parents(fact_id,parent_fact_id) VALUES(?,?)", rows)


def fact_value_json(db, fact_id, request_id, snapshot_id):
    row = db.execute(
        "SELECT value_json FROM facts WHERE fact_id=? AND request_id=? AND snapshot_id=?",
        (fact_id, request_id, snapshot_id),
    ).fetchone()
    return None if row is None else row[0]


def _fact_in_snapshot(db, request_id, snapshot_id, fact_id):
    return (
        db.execute(
            "SELECT 1 FROM facts WHERE request_id=? AND snapshot_id=? AND fact_id=?",
            (request_id, snapshot_id, fact_id),
        ).fetchone()
        is not None
    )


def citable_fact_ids(db, request_id, snapshot_id):
    return {
        row[0]
        for row in db.execute(
            "SELECT fact_id FROM facts WHERE request_id=? AND snapshot_id=? "
            "AND status='observed' AND citable=1",
            (request_id, snapshot_id),
        )
    }


def review_facts(db, request_id, snapshot_id, codes):
    return db.execute(
        "SELECT f.*,EXISTS(SELECT 1 FROM local_fact_lineage l WHERE l.fact_id=f.fact_id) "
        "AS local_lineage FROM facts f WHERE f.request_id=? AND f.snapshot_id=? "
        "AND (f.industry_code IS NULL OR f.industry_code IN ("
        + ",".join("?" for _ in codes)
        + ")) AND (f.metric!='space_fit' OR EXISTS(SELECT 1 FROM space_fit_current c "
        "WHERE c.request_id=f.request_id AND c.snapshot_id=f.snapshot_id "
        "AND c.fact_id=f.fact_id)) ORDER BY f.fact_id",
        [request_id, snapshot_id, *codes],
    ).fetchall()


def _alias_named(db, request_id, alias):
    row = db.execute(
        "SELECT alias FROM fact_aliases WHERE request_id=? AND alias=?",
        (request_id, alias),
    ).fetchone()
    return None if row is None else row[0]


def _alias_of_fact(db, request_id, fact_id):
    row = db.execute(
        "SELECT alias FROM fact_aliases WHERE request_id=? AND fact_id=?",
        (request_id, fact_id),
    ).fetchone()
    return None if row is None else row[0]


def _insert_alias(db, request_id, alias, fact_id):
    db.execute(
        "INSERT INTO fact_aliases(request_id,alias,fact_id) VALUES(?,?,?)",
        (request_id, alias, fact_id),
    )


def _alias(db, request_id, snapshot_id, fact_id):
    existing = _alias_named(db, request_id, fact_id)
    if existing:
        return existing
    row = _alias_of_fact(db, request_id, fact_id)
    if row:
        return row
    if not _fact_in_snapshot(db, request_id, snapshot_id, fact_id):
        raise ValueError("요청에 없는 fact를 별칭으로 내보낼 수 없습니다.")
    for counter in range(8):
        short = sha256(f"{fact_id}:{counter}".encode()).hexdigest()[:8]
        try:
            _insert_alias(db, request_id, short, fact_id)
        except sqlite3.IntegrityError as exc:
            if exc.sqlite_errorcode not in {
                sqlite3.SQLITE_CONSTRAINT_UNIQUE,
                sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY,
            }:
                raise
            row = _alias_of_fact(db, request_id, fact_id)
            if row:
                return row
        else:
            return short
    raise ValueError("별칭 충돌 재시도 8회 한도를 초과했습니다.")


def aliases_for(db, request_id, snapshot_id, fact_ids):
    # 먼저 쓰기 권한을 잡아 조회-삽입 사이의 동시 생성 경합을 막습니다.
    begin_immediate(db)
    return {fact_id: _alias(db, request_id, snapshot_id, fact_id) for fact_id in fact_ids}


def fact_id_by_reference(db, request_id, snapshot_id, reference):
    row = db.execute(
        "SELECT f.fact_id FROM facts f LEFT JOIN fact_aliases a "
        "ON a.fact_id=f.fact_id AND a.request_id=f.request_id "
        "WHERE f.request_id=? AND f.snapshot_id=? AND (f.fact_id=? OR a.alias=?)",
        (request_id, snapshot_id, reference, reference),
    ).fetchone()
    return None if row is None else row[0]


def find_facts(
    db,
    request_id,
    snapshot_id,
    *,
    fact_ids=(),
    industry_code=None,
    source=None,
    metrics=(),
    current_space_fit=False,
):
    query = (
        "SELECT *,EXISTS(SELECT 1 FROM local_fact_lineage l WHERE l.fact_id=facts.fact_id) "
        "AS local_lineage FROM facts WHERE request_id=? AND snapshot_id=?"
    )
    params = [request_id, snapshot_id]
    if fact_ids:
        query += " AND fact_id IN (" + ",".join("?" for _ in fact_ids) + ")"
        params.extend(fact_ids)
    else:
        if industry_code is not None:
            query += " AND industry_code=?"
            params.append(industry_code)
        query += " AND source=? AND metric IN (" + ",".join("?" for _ in metrics) + ")"
        params.extend([source, *metrics])
        if current_space_fit:
            query += (
                " AND fact_id IN (SELECT fact_id FROM space_fit_current "
                "WHERE request_id=? AND snapshot_id=?)"
            )
            params.extend([request_id, snapshot_id])
    cursor = db.execute(query + " ORDER BY fact_id", params)
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def facts_by_ids(db, request_id, snapshot_id, ids):
    cursor = db.execute(
        "SELECT *,EXISTS(SELECT 1 FROM local_fact_lineage l WHERE l.fact_id=facts.fact_id) "
        "AS local_lineage FROM facts WHERE request_id=? AND snapshot_id=? AND fact_id IN ("
        + ",".join("?" for _ in ids)
        + ")",
        [request_id, snapshot_id, *ids],
    )
    names = [c[0] for c in cursor.description]
    return [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]


def current_space_fit_values(db, request_id, snapshot_id):
    return db.execute(
        "SELECT c.industry_code,f.value_json FROM space_fit_current c "
        "JOIN facts f USING(fact_id) WHERE c.request_id=? AND c.snapshot_id=?",
        (request_id, snapshot_id),
    ).fetchall()


def current_space_fit_ids(db, request_id, snapshot_id):
    return db.execute(
        "SELECT fact_id FROM space_fit_current WHERE request_id=? AND snapshot_id=? "
        "ORDER BY industry_code",
        (request_id, snapshot_id),
    ).fetchall()


def space_fit_inputs(db, request_id, snapshot_id):
    return db.execute(
        "SELECT fact_id,industry_code,source,metric,value_json FROM facts "
        "WHERE request_id=? AND snapshot_id=? AND status='observed' AND citable=1 "
        "AND (metric='space_requirements' OR source='user') "
        "ORDER BY created_at DESC,fact_id DESC",
        (request_id, snapshot_id),
    ).fetchall()


def point_space_fit(db, request_id, snapshot_id, industry_code, fact_id):
    db.execute(
        "INSERT INTO space_fit_current(request_id,snapshot_id,industry_code,"
        "fact_id) "
        "VALUES(?,?,?,?) ON CONFLICT(request_id,snapshot_id,industry_code) "
        "DO UPDATE SET fact_id=excluded.fact_id WHERE fact_id!=excluded.fact_id",
        (request_id, snapshot_id, industry_code, fact_id),
    )


def user_space_answers(db, request_id, snapshot_id):
    return db.execute(
        "SELECT fact_id,metric,value_json,unit FROM facts WHERE request_id=? "
        "AND snapshot_id=? AND source='user' AND status='observed' AND citable=1 "
        "AND metric IN ('floor','exclusive_area','existing_facilities') "
        "ORDER BY created_at DESC,fact_id DESC",
        (request_id, snapshot_id),
    ).fetchall()
