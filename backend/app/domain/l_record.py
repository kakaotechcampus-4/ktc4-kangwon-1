from app.domain.contracts import LRecord
from app.domain.report import RULE_SPACE_MESSAGE, l_grade, rule_scored_space
from app.domain.text import has_digit


def assemble_record(item, facts, calls, base_id, base_rows):
    factors = []
    inputs = [(f.fact_id, f.direction, f.severe) for f in item.factors]
    if item.neutral:
        inputs = [(fid, "neutral", False) for fid in item.fact_ids]
    for fid, direction, severe in inputs:
        fact = facts[fid]
        component = None
        claim = (
            "확인한 새 근거의 "
            + {"favorable": "유리 요인", "adverse": "불리 요인", "neutral": "중립 검토"}[direction]
        )
        if fact.metric == "space_fit":
            value = fact.value
            wanted = (
                {"일치"}
                if direction == "favorable"
                else {"불일치"}
                if direction == "adverse"
                else {"일치", "불일치"}
            )
            matched = [
                key
                for key in ("floor", "area", "kitchen", "ventilation", "water_supply")
                if value.get(key) in wanted
            ]
            component = next(
                (key for key in matched if not rule_scored_space(fact, key, item.industry_code)),
                None,
            )
            if component is None:
                raise ValueError(
                    RULE_SPACE_MESSAGE
                    if matched
                    else "해당 없음·미확인은 L 요인이 아닙니다. 확인된 일치/불일치 근거를 쓰세요."
                )
            claim = (
                {
                    "floor": "층",
                    "area": "면적",
                    "kitchen": "주방",
                    "ventilation": "배기",
                    "water_supply": "급배수",
                }[component]
                + " 조건 "
                + value[component]
            )
        elif fact.source == "user":
            value = str(fact.value)
            claim = "·".join(word for word in ("주방", "배기") if word in value) + claim
        factors.append(
            {
                "fact_ids": [fid],
                "direction": direction,
                "major_constraint": severe,
                "space_fit_component": component,
                "claim": claim,
            }
        )
    note_dropped = has_digit(item.note)
    note = "" if note_dropped else item.note
    observed = bool(factors)
    rank = next(i + 1 for i, row in enumerate(base_rows) if row["code"] == item.industry_code)
    return LRecord.model_validate(
        {
            "industry_code": item.industry_code,
            "selection": {
                "basis": "all_industries",
                "code_score_snapshot_id": base_id,
                "code_lower_rank": rank,
                "reason": "전체 업종 동일 기준으로 검토",
            },
            "review_state": "reviewed",
            "status": "observed" if observed else "unknown",
            "grade": l_grade(factors) if observed else None,
            "new_factors": factors,
            "checked_questions": ["코드 점수에 없는 새 조건을 확인했는가"],
            "tool_call_ids": calls,
            "limitations": ([note] if note else [])
            if observed
            else [note or "확인한 새 근거 없음"],
        }
    ), note_dropped
