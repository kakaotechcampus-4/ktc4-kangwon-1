"""PR3에 저장한 점수와 사실을 현재 스냅샷 범위에서 읽습니다."""

from app.ai.tool_contracts import FactsResult, Scorecard, ScorecardResult, ScoreItem
from app.application.ports.storage import open_stores, storage
from app.application.space import rule_answers
from app.domain.contracts import FactView, ScorecardSummary, error
from app.domain.scoring import apply_space, rank_key, score_summary, summarize
from app.domain.space_rules import judge, load_requirements
from app.shared.concurrency import run_in_thread


class InvalidCursor(ValueError):
    """사용자 입력 커서 오류를 저장·계약 오류와 구분합니다."""


def _cursor(value):
    if value is None:
        return 0
    if not value.isdecimal() or int(value) > 100000:
        raise InvalidCursor("잘못된 커서")
    return int(value)


def _scorecards(scope, input):
    with open_stores(scope) as st:
        snapshot = st.scores.latest_score_snapshot(scope.request_id, scope.snapshot_id)
        if snapshot is None:
            return error("SOURCE_UNAVAILABLE", "저장된 코드 점수가 없습니다.")
        answers = rule_answers(scope, stores=st)
        requirements = load_requirements()
        rows = [
            apply_space(
                summarize(r["code"], r["items"], r["regulation"]),
                judge(requirements.get(r["code"], {}), answers),
            )
            for r in snapshot.rows
        ]
        rows.sort(key=lambda r: (r["regulation"] == "금지" or r["space"]["excluded"], rank_key(r)))
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
                        item=r.item,
                        status="not_applicable" if r.status == "n.a." else r.status,
                        grade=r.grade,
                        points=r.points,
                        fact_ids=r.fact_ids,
                        scoring=row["items"][r.item].get("scoring"),
                    )
                    for r in st.scores.industry_scores(snapshot.score_snapshot_id, row["code"])
                ]
                details.append(Scorecard(**fields, items=items))
    return ScorecardResult(
        summaries=summaries,
        scorecards=details,
        next_cursor=str(offset + len(selected)) if offset + len(selected) < len(rows) else None,
    )


def _facts(scope, input):
    storage().provenance.validate_snapshot(scope)
    with open_stores(scope) as st:
        records = st.facts.find_facts(
            scope.request_id,
            scope.snapshot_id,
            fact_ids=input.fact_ids,
            industry_code=input.industry_code,
            source=input.source,
            metrics=input.metrics,
            current_space_fit=input.source == "industry_profile" and input.metrics == ["space_fit"],
        )
        storage().provenance.expand_spatial_scope(scope, records)
        if input.fact_ids and len(records) != len(set(input.fact_ids)):
            return error("UNKNOWN_FACT", "현재 스냅샷에 없는 fact_id입니다.")
        offset = _cursor(input.cursor)
        records_page = records[offset : offset + input.limit]
        facts = [
            FactView(
                fact_id=r.fact_id,
                source=r.source,
                metric=r.metric,
                value=r.value,
                unit=r.unit,
                period=r.period,
                spatial_scope=r.spatial_scope,
                industry_code=r.industry_code,
                status="not_applicable" if r.status == "n.a." else r.status,
                citable=r.citable,
                calc_version=r.calc_version,
                provenance_ref=(
                    "fact_parents:"
                    if r.metric == "space_fit"
                    else "local_fact_lineage:"
                    if r.local_lineage
                    else "fact_sources:"
                )
                + r.fact_id,
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
