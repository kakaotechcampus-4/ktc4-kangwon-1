"""L 근거를 서버에서 검증하고 코드 채점기로 순위·숫자를 다시 만듭니다."""

import json
import re
import uuid
from copy import deepcopy

from app.db.connection import connect
from app.schemas import DecisionResult
from app.storage.raw import _now

from .contracts import FactView, FinalCandidate, LRecord, LSelection
from .reads import score_summary
from .scoring import WEIGHTS, rank_candidates, result, summarize

NEW_METRICS = {
    "place_name",
    "kakao_category",
    "match_status",
    "lq",
    "differentiation",
    "floor",
    "exclusive_area",
    "space_condition",
    "existing_facilities",
    "industry_preferences",
}


class ReportInvalid(ValueError):
    """모델 제출 오류는 수정 가능한 도구 오류로 반환합니다."""


def load_base(scope):
    with connect(scope.path) as db:
        row = db.execute(
            "SELECT score_snapshot_id,summary_json FROM score_snapshots WHERE "
            "request_id=? AND snapshot_id=? ORDER BY created_at LIMIT 1",
            (scope.request_id, scope.snapshot_id),
        ).fetchone()
    if row is None:
        raise ValueError("코드 점수가 없습니다.")
    rows = json.loads(row[1])
    rows.sort(key=lambda r: (-r["lower"], -(r["coverage"] or 0), r["code"]))
    return row[0], rows


def fact_rows(scope, ids):
    from app.local_data.provenance import validate_snapshot

    validate_snapshot(scope)
    if not ids:
        return {}
    with connect(scope.path) as db:
        cursor = db.execute(
            "SELECT *,EXISTS(SELECT 1 FROM local_fact_lineage l WHERE l.fact_id=facts.fact_id) "
            "AS local_lineage FROM facts WHERE request_id=? AND snapshot_id=? AND fact_id IN ("
            + ",".join("?" for _ in ids)
            + ")",
            [scope.request_id, scope.snapshot_id, *ids],
        )
        names = [c[0] for c in cursor.description]
        rows = {r[0]: dict(zip(names, r, strict=True)) for r in cursor.fetchall()}
    from app.local_data.provenance import expand_spatial_scope

    expand_spatial_scope(scope, rows.values())
    if set(rows) != set(ids):
        raise ReportInvalid("현재 스냅샷에 없는 fact_id입니다.")
    return rows


def segments(proposal):
    fields = list(proposal.summary_segments) + list(proposal.limitations_segments)
    for candidate in proposal.candidates + proposal.excluded_candidates:
        fields += (
            candidate.reasons_segments
            + candidate.risks_segments
            + candidate.confirmation_conditions_segments
        )
    return fields


def validate_proposal(scope, proposal, base_id, base_rows, advisor_unavailable=False):
    ranks = {r["code"]: i for i, r in enumerate(base_rows, 1)}
    seen = set()
    extras = set()
    ids = {s.fact_id for s in segments(proposal) if s.type == "fact"}
    for candidate in proposal.candidates + proposal.excluded_candidates:
        ids.update(candidate.fact_ids)
    for record in proposal.L_records:
        if record.industry_code in seen:
            raise ReportInvalid("L 업종이 중복됩니다.")
        seen.add(record.industry_code)
        selection = record.selection
        if selection.code_score_snapshot_id != base_id or selection.code_lower_rank != ranks.get(
            record.industry_code
        ):
            raise ReportInvalid("L 선정의 코드 점수 버전·순위가 다릅니다.")
        if ranks[record.industry_code] > 10:
            if selection.basis != "decision_extra" or not selection.reason_fact_ids:
                raise ReportInvalid("상위 열 업종 밖에는 근거 있는 추가 선정이 필요합니다.")
            extras.add(record.industry_code)
        elif selection.basis != "code_lower_top10":
            raise ReportInvalid("상위 열 업종의 선정 기준이 다릅니다.")
        ids.update(selection.reason_fact_ids)
        for factor in record.new_factors:
            ids.update(factor.fact_ids)
        if record.status == "observed" and not record.new_factors:
            raise ReportInvalid("새 fact 근거가 없으면 L은 unknown입니다.")
    if len(extras) > 2:
        raise ReportInvalid("추가 L 검토는 두 업종까지입니다.")
    facts = fact_rows(scope, ids)
    for s in segments(proposal):
        if s.type == "text" and re.search(r"\d", s.text):
            raise ReportInvalid("문장 숫자는 fact 슬롯으로 제출해야 합니다.")
    for fact in facts.values():
        if fact["status"] != "observed" or not fact["citable"]:
            raise ReportInvalid("미확인 fact는 인용할 수 없습니다.")
    with connect(scope.path) as db:
        code_ids = {
            f
            for r in db.execute(
                "SELECT fact_ids_json FROM scores WHERE score_snapshot_id=? AND item!='L'",
                (base_id,),
            )
            for f in json.loads(r[0])
        }
        for record in proposal.L_records:
            if record.status != "observed":
                continue
            calls = db.execute(
                "SELECT tool_call_id,reply_json FROM tool_calls WHERE request_id=? "
                "AND snapshot_id=? AND actor='decision'",
                (scope.request_id, scope.snapshot_id),
            ).fetchall()
            calls = {r[0]: json.loads(r[1]) for r in calls}
            valid_calls = {k for k, v in calls.items() if v["status"] in {"ok", "partial"}}
            if not set(record.tool_call_ids) <= valid_calls:
                raise ReportInvalid("L 도구 기록이 실제 성공한 호출과 다릅니다.")
            call_text = json.dumps([calls[k] for k in record.tool_call_ids])
            claims = [f.claim.strip() for f in record.new_factors]
            evidence_sets = [tuple(sorted(set(f.fact_ids))) for f in record.new_factors]
            if len(set(claims)) != len(claims) or len(set(evidence_sets)) != len(evidence_sets):
                raise ReportInvalid("같은 새 요인·근거를 중복해 등급을 올릴 수 없습니다.")
            for factor in record.new_factors:
                if factor.major_constraint and factor.direction != "adverse":
                    raise ReportInvalid("큰 운영 제약은 불리 요인으로 기록해야 합니다.")
                if any(
                    f in code_ids or facts[f]["metric"] not in NEW_METRICS for f in factor.fact_ids
                ):
                    raise ReportInvalid("D/C/S 코드 점수 요인을 L에 중복 채점할 수 없습니다.")
                if any(f not in call_text for f in factor.fact_ids):
                    raise ReportInvalid("L 근거는 실제 조회한 fact여야 합니다.")
            favorable = sum(f.direction == "favorable" for f in record.new_factors)
            adverse = sum(f.direction == "adverse" for f in record.new_factors)
            major = any(f.major_constraint for f in record.new_factors)
            if (
                record.grade == 4
                and (favorable < 2 or adverse)
                or record.grade == 3
                and (favorable < 1 or adverse)
                or record.grade == 2
                and bool(favorable) != bool(adverse)
                or record.grade == 1
                and (adverse != 1 or major)
                or record.grade == 0
                and (adverse < 2 and not major)
            ):
                raise ReportInvalid("L 등급과 새 유리·불리 요인 개수가 맞지 않습니다.")
            if record.advisor_consult_ids:
                found = db.execute(
                    "SELECT consult_id FROM advisor_consults WHERE request_id=? AND snapshot_id=?",
                    (scope.request_id, scope.snapshot_id),
                ).fetchall()
                if not set(record.advisor_consult_ids) <= {r[0] for r in found}:
                    raise ReportInvalid("자문 기록이 현재 요청에 없습니다.")
            record.advisor_unavailable = record.advisor_unavailable or advisor_unavailable
    return facts


def render_segment(segment, facts):
    if segment.type == "text":
        return segment.text
    fact = facts[segment.fact_id]
    value = json.loads(fact["value_json"])
    if segment.format == "text":
        return str(value)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ReportInvalid("숫자 형식에 맞지 않는 fact입니다.")
    if segment.format == "percent":
        if fact["unit"] not in {"%", "비율"}:
            raise ReportInvalid("백분율 단위가 아닙니다.")
        return f"{value * 100 if fact['unit'] == '비율' else value:.1f}%"
    if segment.format == "count":
        return f"{value:,.0f}"
    if segment.format == "distance":
        return f"{value:,.0f}m"
    return f"{value:.2f}"


def finalize(
    scope,
    proposal,
    base_id,
    base_rows,
    *,
    limitations=(),
    advisor_unavailable=False,
    regulation_result=None,
    reviews=None,
    resolutions=(),
):
    facts = validate_proposal(scope, proposal, base_id, base_rows, advisor_unavailable)
    if reviews is not None:
        expected = {i.issue_id for r in reviews for i in r.issues}
        if len(resolutions) != len(expected) or {r.issue_id for r in resolutions} != expected:
            raise ReportInvalid("모든 평가 지적에 중복 없는 반영 결정이 필요합니다.")
        ids = {f for r in reviews for i in r.issues for f in i.fact_ids}
        ids.update(f for r in resolutions for f in r.fact_ids)
        extra = fact_rows(scope, ids)
        if any(f["status"] != "observed" or not f["citable"] for f in extra.values()):
            raise ReportInvalid("검토 반영 근거를 인용할 수 없습니다.")
        facts.update(extra)
    records = {r.industry_code: r for r in proposal.L_records}
    rows = []
    all_records = []
    restrictions = (
        {r.industry_code: r.status for r in regulation_result.industry_restrictions}
        if regulation_result
        else {}
    )
    for rank, original in enumerate(base_rows, 1):
        record = records.get(original["code"])
        if record is None:
            record = LRecord(
                industry_code=original["code"],
                selection=LSelection(
                    basis="code_lower_top10" if rank <= 10 else "outside_scope",
                    code_score_snapshot_id=base_id,
                    code_lower_rank=rank,
                    reason="코드 하한 기준 검토 범위",
                ),
                review_state="unreviewed",
                status="unknown",
                grade=None,
                advisor_unavailable=advisor_unavailable,
            )
        record.advisor_unavailable = record.advisor_unavailable or advisor_unavailable
        all_records.append(record)
        items = deepcopy(original["items"])
        items["L"] = result("L", record.grade if record.status == "observed" else None)
        rows.append(
            summarize(
                original["code"], items, restrictions.get(original["code"], original["regulation"])
            )
        )
    score_id = "ss_" + str(uuid.uuid4())
    report_id = "report_" + str(uuid.uuid4())
    candidates = {c.industry_code: c for c in proposal.candidates + proposal.excluded_candidates}
    top = []
    for row in rank_candidates(rows)[:5]:
        candidate = candidates.get(row["code"])
        top.append(
            FinalCandidate(
                **score_summary(row),
                industry_name=row["name"],
                reasons_segments=candidate.reasons_segments if candidate else [],
                risks_segments=candidate.risks_segments if candidate else [],
                confirmation_conditions_segments=candidate.confirmation_conditions_segments
                if candidate
                else [],
                fact_ids=candidate.fact_ids if candidate else [],
                review_state=records[row["code"]].review_state
                if row["code"] in records
                else "unreviewed",
            )
        )
    views = [
        FactView(
            fact_id=f["fact_id"],
            source=f["source"],
            metric=f["metric"],
            value=json.loads(f["value_json"]),
            unit=f["unit"],
            period=f["period"],
            spatial_scope=json.loads(f["spatial_scope_json"]),
            industry_code=f["industry_code"],
            status=f["status"],
            citable=bool(f["citable"]),
            calc_version=f["calc_version"],
            provenance_ref=("local_fact_lineage:" if f["local_lineage"] else "fact_sources:")
            + f["fact_id"],
        )
        for f in facts.values()
    ]
    from .contracts import TextSegment

    result_model = DecisionResult(
        request_id=scope.request_id,
        run_id=scope.run_id,
        report_id=report_id,
        snapshot_id=scope.snapshot_id,
        score_snapshot_id=score_id,
        summary_segments=proposal.summary_segments,
        top5=top,
        facts=views,
        L_records=all_records,
        evaluator_reviews=reviews
        if reviews is not None
        else [
            {"actor": actor, "status": "failed", "issues": [], "error_code": "SOURCE_UNAVAILABLE"}
            for actor in ["examiner", "founder", "customer", "landlord_advocate"]
        ],
        review_completeness=sum(r.status == "completed" for r in reviews) / 4 if reviews else 0,
        review_resolutions=list(resolutions),
        confirmation_conditions_segments=[],
        limitations_segments=proposal.limitations_segments
        + [
            TextSegment(type="text", text=t)
            for t in [
                *limitations,
                *(
                    ["평가 미완료: 실패한 평가를 동의로 간주하지 않습니다."]
                    if reviews and any(r.status == "failed" for r in reviews)
                    else []
                ),
            ]
        ],
    )
    rendered = {
        "summary": "".join(render_segment(s, facts) for s in proposal.summary_segments),
        "top5": [
            {
                "industry_code": c.industry_code,
                "reasons": "".join(render_segment(s, facts) for s in c.reasons_segments),
            }
            for c in top
        ],
    }
    with connect(scope.path) as db:
        db.execute(
            "INSERT INTO score_snapshots VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                score_id,
                scope.request_id,
                scope.snapshot_id,
                scope.run_id,
                "v0.8",
                "rubric-v0.8-pr5",
                json.dumps(rows, ensure_ascii=False),
                json.dumps([r.industry_code for r in top]),
                "reviewed" if records else "unreviewed",
                _now(),
            ),
        )
        for row in rows:
            for item, score in row["items"].items():
                ids = (
                    [f for factor in records[row["code"]].new_factors for f in factor.fact_ids]
                    if item == "L" and row["code"] in records
                    else []
                )
                if item != "L":
                    ids = json.loads(
                        db.execute(
                            "SELECT fact_ids_json FROM scores WHERE score_snapshot_id=? AND "
                            "industry_code=? AND item=?",
                            (base_id, row["code"], item),
                        ).fetchone()[0]
                    )
                db.execute(
                    "INSERT INTO scores VALUES(?,?,?,?,?,?,?,?)",
                    (
                        score_id,
                        row["code"],
                        item,
                        WEIGHTS[item],
                        score["status"],
                        score["grade"],
                        score["points"],
                        json.dumps(ids),
                    ),
                )
        db.execute(
            "INSERT INTO agentic_reports VALUES(?,?,?,?,?,?,?,?)",
            (
                report_id,
                scope.request_id,
                scope.snapshot_id,
                proposal.model_dump_json(),
                result_model.model_dump_json(),
                json.dumps(rendered, ensure_ascii=False),
                "final" if reviews is not None else "draft_candidate",
                _now(),
            ),
        )
    return result_model
