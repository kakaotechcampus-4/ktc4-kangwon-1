"""L 근거를 서버에서 검증하고 코드 채점기로 순위·숫자를 다시 만듭니다."""

import json
import uuid
from copy import deepcopy

from app.application.ports.storage import open_stores, storage
from app.application.space import rule_answers
from app.domain.code90 import METHOD
from app.domain.contracts import (
    EVALUATOR_ACTORS,
    EVALUATOR_COUNT,
    FactView,
    FinalCandidate,
)
from app.domain.report import (
    ReportInvalid,
    code90_uses_metric,
    complete_l_records,
    condition_excluded,
    industry_ranking,
    join_segments,
    l_grade,
    limitation_segments,
    regulation_excluded,
    rule_scored_space,
    segments,
)
from app.domain.schemas import DecisionResult
from app.domain.scoring import (
    WEIGHTS,
    apply_space,
    rank_candidates,
    rank_key,
    result,
    score_summary,
    summarize,
)
from app.domain.space_rules import judge, load_requirements
from app.domain.text import has_digit
from app.shared.clock import utc_now_iso

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


def load_base(scope):
    with open_stores(scope.path) as st:
        row = st.scores.first_score_snapshot(scope.request_id, scope.snapshot_id)
    if row is None:
        raise ValueError("코드 점수가 없습니다.")
    rows = json.loads(row[1])
    rows.sort(key=rank_key)
    return row[0], rows


def fact_rows(scope, ids):
    storage().provenance.validate_snapshot(scope)
    if not ids:
        return {}
    with open_stores(scope.path) as st:
        rows = {
            r["fact_id"]: r for r in st.facts.facts_by_ids(scope.request_id, scope.snapshot_id, ids)
        }
    storage().provenance.expand_spatial_scope(scope, rows.values())
    if set(rows) != set(ids):
        raise ReportInvalid("현재 스냅샷에 없는 fact_id입니다.")
    return rows


def validate_l_records(scope, records, base_id, base_rows, advisor_unavailable=False):
    ranks = {r["code"]: i for i, r in enumerate(base_rows, 1)}
    original_rows = {r["code"]: r for r in base_rows}
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
    with open_stores(scope.path) as st:
        code_ids = {f for r in st.scores.code_item_fact_ids(base_id) for f in json.loads(r[0])}
        space_values = {
            row[0]: json.loads(row[1])
            for row in st.facts.current_space_fit_values(scope.request_id, scope.snapshot_id)
        }
        for record in records:
            if record.status != "observed":
                continue
            calls = st.agentic.decision_tool_calls(scope.request_id, scope.snapshot_id)
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
                    f in code_ids
                    or facts[f]["metric"] not in NEW_METRICS
                    or code90_uses_metric(original_rows[record.industry_code], facts[f]["metric"])
                    for f in factor.fact_ids
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
                found = st.agentic.advisor_consult_ids(scope.request_id, scope.snapshot_id)
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


def recompute_l_scores(scope, records, base_id, base_rows, regulation_result=None):
    restrictions = (
        {r.industry_code: r.status for r in regulation_result.industry_restrictions}
        if regulation_result
        else {}
    )
    indexed = {r.industry_code: r for r in records}
    answers = rule_answers(scope)
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
    with open_stores(scope.path) as st:
        st.scores.insert_score_snapshot(
            (
                score_id,
                scope.request_id,
                scope.snapshot_id,
                scope.run_id,
                "v0.8",
                METHOD if any("code90" in row for row in rows) else "rubric-v0.8-pr5",
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
                    else json.loads(st.scores.item_fact_ids_json(base_id, row["code"], item))
                )
                st.scores.insert_score(
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
        ranking=industry_ranking(rows, excluded_codes),
        regulation_excluded=regulation_excluded(rows),
        facts=views,
        L_records=all_records,
        evaluator_reviews=reviews
        if reviews is not None
        else [
            {"actor": actor, "status": "failed", "issues": [], "error_code": "SOURCE_UNAVAILABLE"}
            for actor in EVALUATOR_ACTORS
        ],
        review_completeness=sum(r.status == "completed" for r in reviews) / EVALUATOR_COUNT
        if reviews
        else 0,
        review_resolutions=list(resolutions),
        confirmation_conditions_segments=[],
        limitations_segments=limitation_segments(
            proposal.limitations_segments,
            [
                *limitations,
                *(
                    ["평가 미완료: 실패한 평가를 동의로 간주하지 않습니다."]
                    if reviews and any(r.status == "failed" for r in reviews)
                    else []
                ),
            ],
        ),
    )
    rendered = {
        "summary": join_segments(proposal.summary_segments, facts),
        "top5": [
            {
                "industry_code": c.industry_code,
                "reasons": join_segments(c.reasons_segments, facts),
            }
            for c in top
        ],
    }
    with open_stores(scope.path) as st:
        st.agentic.insert_report(
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
