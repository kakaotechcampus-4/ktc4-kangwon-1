"""fact·별칭·공간 비교 포인터를 읽고 씁니다."""


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
    db.execute("INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)


def insert_local_fact_lineage(db, fact_id, ref, row_key, column):
    db.execute("INSERT INTO local_fact_lineage VALUES(?,?,?,?)", (fact_id, ref, row_key, column))


def insert_fact_sources(db, rows):
    db.executemany("INSERT INTO fact_sources VALUES(?,?,?)", rows)


def insert_fact_parents(db, rows):
    db.executemany("INSERT INTO fact_parents VALUES(?,?)", rows)


def fact_value_json(db, fact_id, request_id, snapshot_id):
    row = db.execute(
        "SELECT value_json FROM facts WHERE fact_id=? AND request_id=? AND snapshot_id=?",
        (fact_id, request_id, snapshot_id),
    ).fetchone()
    return None if row is None else row[0]


def fact_in_snapshot(db, request_id, snapshot_id, fact_id):
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


def alias_named(db, request_id, alias):
    row = db.execute(
        "SELECT alias FROM fact_aliases WHERE request_id=? AND alias=?",
        (request_id, alias),
    ).fetchone()
    return None if row is None else row[0]


def alias_of_fact(db, request_id, fact_id):
    row = db.execute(
        "SELECT alias FROM fact_aliases WHERE request_id=? AND fact_id=?",
        (request_id, fact_id),
    ).fetchone()
    return None if row is None else row[0]


def insert_alias(db, request_id, alias, fact_id):
    db.execute("INSERT INTO fact_aliases VALUES(?,?,?)", (request_id, alias, fact_id))


def fact_id_by_reference(db, request_id, snapshot_id, reference):
    row = db.execute(
        "SELECT f.fact_id FROM facts f LEFT JOIN fact_aliases a "
        "ON a.fact_id=f.fact_id AND a.request_id=f.request_id "
        "WHERE f.request_id=? AND f.snapshot_id=? AND (f.fact_id=? OR a.alias=?)",
        (request_id, snapshot_id, reference, reference),
    ).fetchone()
    return None if row is None else row[0]
