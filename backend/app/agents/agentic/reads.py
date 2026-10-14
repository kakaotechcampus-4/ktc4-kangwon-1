"""PR3에 저장한 점수와 사실을 현재 스냅샷 범위에서 읽습니다."""

import json

from app.concurrency import run_in_thread
from app.db.connection import connect
from app.local_data.provenance import expand_spatial_scope, validate_snapshot

from .contracts import (
    FactsResult,
    FactView,
    Scorecard,
    ScorecardResult,
    ScorecardSummary,
    ScoreItem,
)
from .raw_query import error


class InvalidCursor(ValueError):
    """사용자 입력 커서 오류를 저장·계약 오류와 구분합니다."""


def _cursor(value):
    if value is None:
        return 0
    if not value.isdecimal() or int(value) > 100000:
        raise InvalidCursor("잘못된 커서")
    return int(value)


def _scorecards(scope, input):
    with connect(scope.path) as db:
        snapshot = db.execute(
            "SELECT score_snapshot_id,summary_json FROM score_snapshots "
            "WHERE request_id=? AND snapshot_id=? ORDER BY created_at DESC LIMIT 1",
            (scope.request_id, scope.snapshot_id),
        ).fetchone()
        if snapshot is None:
            return error("SOURCE_UNAVAILABLE", "저장된 코드 점수가 없습니다.")
        rows = json.loads(snapshot[1])
        rows.sort(key=lambda r: (-r["lower"], -(r["coverage"] or 0), r["code"]))
        if input.industry_codes:
            rows = [r for r in rows if r["code"] in input.industry_codes]
        offset = _cursor(input.cursor)
        selected = rows[offset : offset + input.limit]
        summaries, details = [], []
        for row in selected:
            fields = score_summary(row)
            if input.mode == "summary":
                summaries.append(ScorecardSummary(**fields))
            else:
                items = [
                    ScoreItem(
                        item=r[0],
                        status="not_applicable" if r[1] == "n.a." else r[1],
                        grade=r[2],
                        points=r[3],
                        fact_ids=json.loads(r[4]),
                    )
                    for r in db.execute(
                        "SELECT item,status,grade,points,fact_ids_json FROM scores "
                        "WHERE score_snapshot_id=? AND industry_code=?",
                        (snapshot[0], row["code"]),
                    )
                ]
                details.append(Scorecard(**fields, items=items))
    return ScorecardResult(
        summaries=summaries,
        scorecards=details,
        next_cursor=str(offset + len(selected)) if offset + len(selected) < len(rows) else None,
    )


def _facts(scope, input):
    validate_snapshot(scope)
    with connect(scope.path) as db:
        query = (
            "SELECT *,EXISTS(SELECT 1 FROM local_fact_lineage l WHERE l.fact_id=facts.fact_id) "
            "AS local_lineage FROM facts WHERE request_id=? AND snapshot_id=?"
        )
        params = [scope.request_id, scope.snapshot_id]
        if input.fact_ids:
            query += " AND fact_id IN (" + ",".join("?" for _ in input.fact_ids) + ")"
            params.extend(input.fact_ids)
        else:
            query += (
                " AND industry_code=? AND source=? AND metric IN ("
                + ",".join("?" for _ in input.metrics)
                + ")"
            )
            params.extend([input.industry_code, input.source, *input.metrics])
        cursor = db.execute(query + " ORDER BY fact_id", params)
        columns = [c[0] for c in cursor.description]
        records = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        expand_spatial_scope(scope, records)
        if input.fact_ids and len(records) != len(set(input.fact_ids)):
            return error("UNKNOWN_FACT", "현재 스냅샷에 없는 fact_id입니다.")
        offset = _cursor(input.cursor)
        records_page = records[offset : offset + input.limit]
        facts = [
            FactView(
                fact_id=r["fact_id"],
                source=r["source"],
                metric=r["metric"],
                value=json.loads(r["value_json"]),
                unit=r["unit"],
                period=r["period"],
                spatial_scope=json.loads(r["spatial_scope_json"]),
                industry_code=r["industry_code"],
                status="not_applicable" if r["status"] == "n.a." else r["status"],
                citable=bool(r["citable"]),
                calc_version=r["calc_version"],
                provenance_ref=("local_fact_lineage:" if r["local_lineage"] else "fact_sources:")
                + r["fact_id"],
            )
            for r in records_page
        ]
    return FactsResult(
        facts=facts,
        provenance_refs=[f.provenance_ref for f in facts],
        next_cursor=str(offset + len(facts)) if offset + len(facts) < len(records) else None,
    )


async def get_scorecard(scope, input):
    return await run_in_thread(_scorecards, scope, input)


async def get_facts(scope, input):
    return await run_in_thread(_facts, scope, input)


def score_summary(row):
    fields = dict(
        industry_code=row["code"],
        code_points=row["lower"] - (row["items"]["L"]["points"] or 0),
        L_points=row["items"]["L"]["points"],
        L_status=row["items"]["L"]["status"],
        A=row["applicable_weight"],
        B=row["lower"],
        H=row["upper"],
        lower_ratio=row["lower_ratio"],
        upper_ratio=row["upper_ratio"],
        coverage=row["coverage"],
        demand_coverage=row["d_coverage"],
        competition_coverage=row["c_coverage"],
        G=row["regulation"],
        badge=row["badge"],
        confirmation_conditions=row["confirmation_conditions"],
    )
    return fields
