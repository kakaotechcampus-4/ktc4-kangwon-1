"""L 근거를 서버에서 검증하고 코드 채점기로 순위·숫자를 다시 만듭니다."""

import json
import uuid
from copy import deepcopy

from app.clock import utc_now_iso
from app.db.connection import connect
from app.industries.catalog import INDUSTRIES
from app.local_data.provenance import expand_spatial_scope, validate_snapshot
from app.schemas import DecisionResult
from app.text import has_digit

from .contracts import (
    ConditionExcludedCandidate,
    FactView,
    FinalCandidate,
    LRecord,
    LSelection,
)
from .read_tools import score_summary
from .scoring import WEIGHTS, apply_space, rank_candidates, rank_key, result, summarize
from .space import confirmed_answers
from .space_rules import FACILITY_NAMES, FACILITY_STATE_TEXT, judge, load_requirements

RULE_FACILITY_LEVELS = frozenset({"required", "preferred"})
RULE_SPACE_MESSAGE = "층과 필수·선호 공간 조건은 규칙이 채점합니다. L 근거로 쓸 수 없습니다."
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
    "space_fit",
}


class ReportInvalid(ValueError):
    """모델 제출 오류는 수정 가능한 도구 오류로 반환합니다."""


def l_grade(factors):
    favorable = sum(f["direction"] == "favorable" for f in factors)
    adverse = sum(f["direction"] == "adverse" for f in factors)
    if adverse >= 2 or any(f.get("major_constraint") for f in factors):
        return 0
    if favorable and adverse or not favorable and not adverse:
        return 2
    if adverse:
        return 1
    return 4 if favorable >= 2 else 3


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


def rule_scored_space(fact, component, industry_code):
    metric = fact.get("metric")
    if metric == "space_fit":
        if component == "floor":
            return True
        level = load_requirements().get(industry_code, {}).get(f"{component}_needed")
        return component in FACILITY_NAMES and level in RULE_FACILITY_LEVELS
    if fact.get("source") != "user":
        return False
    if metric == "floor":
        return True
    raw = fact.get("value_json")
    return metric == "existing_facilities" and raw is not None and isinstance(json.loads(raw), dict)


def condition_excluded(rows):
    ranked = sorted((r for r in rows if r["regulation"] != "금지"), key=rank_key)
    return [
        ConditionExcludedCandidate(
            industry_code=r["code"],
            industry_name=r["name"],
            reasons=r["space"]["exclusion_reasons"],
            score_rank=rank,
        )
        for rank, r in enumerate(ranked, 1)
        if r.get("space", {}).get("excluded", False)
    ]


def fact_rows(scope, ids):
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


def validate_l_records(scope, records, base_id, base_rows, advisor_unavailable=False):
    ranks = {r["code"]: i for i, r in enumerate(base_rows, 1)}
    seen = set()
    ids = set()
    for record in records:
        if record.industry_code in seen:
            raise ReportInvalid("L 업종이 중복됩니다.")
        seen.add(record.industry_code)
        selection = record.selection
        if selection.code_score_snapshot_id != base_id or selection.code_lower_rank != ranks.get(
            record.industry_code
        ):
            raise ReportInvalid("L 선정의 코드 점수 버전·순위가 다릅니다.")
        if selection.basis != "all_industries":
            raise ReportInvalid("L은 전체 업종을 같은 기준으로 검토해야 합니다.")
        if record.status == "unknown" and not record.limitations:
            raise ReportInvalid("unknown L에는 개별 이유가 필요합니다.")
        ids.update(selection.reason_fact_ids)
        for factor in record.new_factors:
            ids.update(factor.fact_ids)
        if record.status == "observed" and not record.new_factors:
            raise ReportInvalid("새 fact 근거가 없으면 L은 unknown입니다.")
    facts = fact_rows(scope, ids)
    free_texts = []
    for record in records:
        free_texts += [record.selection.reason, *record.checked_questions, *record.limitations]
        free_texts += [factor.claim for factor in record.new_factors]
    if any(has_digit(text) for text in free_texts):
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
        space_values = {
            row[0]: json.loads(row[1])
            for row in db.execute(
                "SELECT c.industry_code,f.value_json FROM space_fit_current c "
                "JOIN facts f USING(fact_id) WHERE c.request_id=? AND c.snapshot_id=?",
                (scope.request_id, scope.snapshot_id),
            )
        }
        for record in records:
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
            evidence_sets = [
                {
                    (
                        fid,
                        factor.space_fit_component if facts[fid]["metric"] == "space_fit" else None,
                    )
                    for fid in factor.fact_ids
                }
                for factor in record.new_factors
            ]
            if len(set(claims)) != len(claims) or sum(map(len, evidence_sets)) != len(
                set().union(*evidence_sets)
            ):
                raise ReportInvalid("같은 새 요인·근거를 중복해 등급을 올릴 수 없습니다.")
            for factor in record.new_factors:
                if factor.direction == "adverse" and any(
                    facts[f].get("source") == "user" for f in factor.fact_ids
                ):
                    components = {
                        key
                        for word, key in (("주방", "kitchen"), ("배기", "ventilation"))
                        if word in factor.claim or factor.space_fit_component == key
                    }
                    if any(
                        space_values.get(record.industry_code, {}).get(key) == "해당 없음"
                        for key in components
                    ):
                        raise ReportInvalid(
                            "해당 없는 주방·배기 요건의 부재는 불리 요인이 아닙니다."
                        )
                if any(
                    facts[f]["industry_code"] not in (None, record.industry_code)
                    for f in factor.fact_ids
                ):
                    raise ReportInvalid("L 근거의 업종이 검토 업종과 다릅니다.")
                if any(
                    rule_scored_space(facts[f], factor.space_fit_component, record.industry_code)
                    for f in factor.fact_ids
                ):
                    raise ReportInvalid(RULE_SPACE_MESSAGE)
                if factor.major_constraint and factor.direction != "adverse":
                    raise ReportInvalid("큰 운영 제약은 불리 요인으로 기록해야 합니다.")
                if any(
                    f in code_ids or facts[f]["metric"] not in NEW_METRICS for f in factor.fact_ids
                ):
                    raise ReportInvalid("D/C/S 코드 점수 요인을 L에 중복 채점할 수 없습니다.")
                if any(f not in call_text for f in factor.fact_ids):
                    raise ReportInvalid("L 근거는 실제 조회한 fact여야 합니다.")
                for fid in factor.fact_ids:
                    if facts[fid]["metric"] != "space_fit":
                        continue
                    fit = json.loads(facts[fid]["value_json"])
                    component = factor.space_fit_component
                    allowed = (
                        {"일치"}
                        if factor.direction == "favorable"
                        else {"불일치"}
                        if factor.direction == "adverse"
                        else {"일치", "불일치"}
                    )
                    if component is None or fit.get(component) not in allowed:
                        raise ReportInvalid(
                            "공간 요건의 확인된 일치·불일치만 L 요인으로 쓸 수 있습니다."
                        )
            if record.grade != l_grade([factor.model_dump() for factor in record.new_factors]):
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


def validate_proposal(scope, proposal):
    ids = {s.fact_id for s in segments(proposal) if s.type == "fact"}
    for candidate in proposal.candidates + proposal.excluded_candidates:
        ids.update(candidate.fact_ids)
    if any(has_digit(s.text) for s in segments(proposal) if s.type == "text"):
        raise ReportInvalid("문장 숫자는 fact 슬롯으로 제출해야 합니다.")
    facts = fact_rows(scope, ids)
    if any(f["status"] != "observed" or not f["citable"] for f in facts.values()):
        raise ReportInvalid("미확인 fact는 인용할 수 없습니다.")
    return facts


def complete_l_records(records, base_id, base_rows, advisor_unavailable=False):
    indexed = {r.industry_code: r for r in records}
    if len(indexed) != len(records):
        raise ReportInvalid("L 업종이 중복됩니다.")
    if {row["code"] for row in base_rows} != set(INDUSTRIES):
        raise ReportInvalid("전체 업종의 초기 코드 점수가 필요합니다.")
    completed = []
    for rank, original in enumerate(base_rows, 1):
        record = indexed.get(original["code"])
        if record is None:
            record = LRecord(
                industry_code=original["code"],
                selection=LSelection(
                    basis="all_industries",
                    code_score_snapshot_id=base_id,
                    code_lower_rank=rank,
                    reason="전체 업종 검토",
                ),
                review_state="unreviewed",
                status="unknown",
                grade=None,
                limitations=["L 판단 미제출: 확인된 새 근거를 제출하지 않았습니다."],
            )
        record.advisor_unavailable = record.advisor_unavailable or advisor_unavailable
        completed.append(record)
    return completed


def recompute_l_scores(scope, records, base_id, base_rows, regulation_result=None):
    restrictions = (
        {r.industry_code: r.status for r in regulation_result.industry_restrictions}
        if regulation_result
        else {}
    )
    indexed = {r.industry_code: r for r in records}
    answers = confirmed_answers(scope)
    requirements = load_requirements()
    rows = []
    for original in base_rows:
        record = indexed[original["code"]]
        items = deepcopy(original["items"])
        items["L"] = result("L", record.grade if record.status == "observed" else None)
        scored = summarize(
            original["code"], items, restrictions.get(original["code"], original["regulation"])
        )
        rows.append(apply_space(scored, judge(requirements.get(original["code"], {}), answers)))
    score_id = "ss_" + str(uuid.uuid4())
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
                json.dumps([r["code"] for r in rank_candidates(rows)[:5]]),
                "reviewed",
                utc_now_iso(),
            ),
        )
        for row in rows:
            for item, score in row["items"].items():
                ids = (
                    [f for factor in indexed[row["code"]].new_factors for f in factor.fact_ids]
                    if item == "L"
                    else json.loads(
                        db.execute(
                            "SELECT fact_ids_json FROM scores WHERE score_snapshot_id=? "
                            "AND industry_code=? AND item=?",
                            (base_id, row["code"], item),
                        ).fetchone()[0]
                    )
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
    return score_id, rows


def render_segment(segment, facts):
    if segment.type == "text":
        return segment.text
    fact = facts[segment.fact_id]
    value = json.loads(fact["value_json"])
    if segment.format == "text":
        if fact["metric"] == "existing_facilities" and isinstance(value, dict):
            return " · ".join(
                f"{name} {FACILITY_STATE_TEXT[value[key]]}"
                for key, name in FACILITY_NAMES.items()
                if value.get(key) in FACILITY_STATE_TEXT
            )
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
    l_records=(),
    limitations=(),
    advisor_unavailable=False,
    regulation_result=None,
    reviews=None,
    resolutions=(),
):
    if any(
        has_digit(text)
        for resolution in resolutions
        for text in [resolution.reason, *resolution.applied, *resolution.not_applied]
    ):
        raise ReportInvalid("검토 반영 문장 숫자는 fact 슬롯으로 제출해야 합니다.")
    facts = validate_proposal(scope, proposal)
    all_records = complete_l_records(l_records, base_id, base_rows, advisor_unavailable)
    facts.update(validate_l_records(scope, all_records, base_id, base_rows, advisor_unavailable))
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
    records = {r.industry_code: r for r in all_records}
    score_id, rows = recompute_l_scores(scope, all_records, base_id, base_rows, regulation_result)
    report_id = "report_" + str(uuid.uuid4())
    candidates = {c.industry_code: c for c in proposal.candidates + proposal.excluded_candidates}

    def candidate_model(row):
        candidate = candidates.get(row["code"])
        return FinalCandidate(
            **score_summary(row),
            industry_name=row["name"],
            reasons_segments=candidate.reasons_segments if candidate else [],
            risks_segments=candidate.risks_segments if candidate else [],
            confirmation_conditions_segments=candidate.confirmation_conditions_segments
            if candidate
            else [],
            fact_ids=candidate.fact_ids if candidate else [],
            review_state=records[row["code"]].review_state,
        )

    top = [candidate_model(row) for row in rank_candidates(rows)[:5]]
    excluded_codes = {candidate.industry_code for candidate in proposal.excluded_candidates}
    excluded = [candidate_model(row) for row in rows if row["code"] in excluded_codes]
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
            provenance_ref=(
                "fact_parents:"
                if f["metric"] == "space_fit"
                else "local_fact_lineage:"
                if f["local_lineage"]
                else "fact_sources:"
            )
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
        excluded_candidates=excluded,
        condition_excluded=condition_excluded(rows),
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
            "INSERT INTO agentic_reports VALUES(?,?,?,?,?,?,?,?)",
            (
                report_id,
                scope.request_id,
                scope.snapshot_id,
                proposal.model_dump_json(),
                result_model.model_dump_json(),
                json.dumps(rendered, ensure_ascii=False),
                "final" if reviews is not None else "draft_candidate",
                utc_now_iso(),
            ),
        )
    return result_model
