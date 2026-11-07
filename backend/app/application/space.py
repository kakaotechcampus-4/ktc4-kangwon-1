"""업종 공간 요건을 명시된 임대인 답변과만 대조합니다."""

import json
from contextlib import nullcontext

from app.application.facts import register_fact
from app.application.ports.storage import open_stores
from app.domain.industries.catalog import INDUSTRIES
from app.domain.space_fit import chosen_answer, compare_space
from app.domain.space_values import (
    readable_answer,
)

CONFIRMED_UNIT = "확인 화면 확정값"


def rule_answers(scope, *, stores=None):
    with open_stores(scope.path) if stores is None else nullcontext(stores) as st:
        rows = st.facts.user_space_answers(scope.request_id, scope.snapshot_id)
    answers, candidates = {}, {}
    for fact_id, metric, raw, unit in rows:
        value = json.loads(raw)
        if metric == "existing_facilities":
            if isinstance(value, dict) and unit == CONFIRMED_UNIT:
                answers.setdefault("confirmed_facilities", value)
        else:
            candidates.setdefault(metric, []).append((fact_id, value))
    for metric, found in candidates.items():
        chosen = chosen_answer(metric, found)
        if readable_answer(metric, chosen[1]):
            answers[metric] = chosen[1]
    return answers


def ensure_space_fits(scope, *, stores=None):
    """비교 값·부모 계보가 바뀌면 새 fact를 만들고 현재 포인터만 갱신합니다."""
    with open_stores(scope.path) if stores is None else nullcontext(stores) as st:
        st.begin_immediate()
        profiles, answers, answer_ids, candidates = {}, {}, {}, {}
        for row in st.facts.space_fit_inputs(scope.request_id, scope.snapshot_id):
            if row[2] == "industry_profile" and row[3] == "space_requirements":
                profiles.setdefault(row[1], (row[0], json.loads(row[4])))
            elif row[2] == "user" and row[3] in {
                "floor",
                "exclusive_area",
                "existing_facilities",
                "space_condition",
            }:
                value = json.loads(row[4])
                key = (
                    "confirmed_facilities"
                    if row[3] == "existing_facilities" and isinstance(value, dict)
                    else row[3]
                )
                candidates.setdefault(key, []).append((row[0], value))
        for metric, rows in candidates.items():
            if metric in {"floor", "exclusive_area"}:
                chosen = chosen_answer(metric, rows)
            else:
                chosen = rows[0]
            answer_ids[metric], answers[metric] = chosen
        if set(profiles) != set(INDUSTRIES):
            raise ValueError("공간 비교에는 51업종의 공간 요건 원문 fact가 필요합니다.")
        current = {}
        for code in sorted(INDUSTRIES):
            profile_id, profile = profiles[code]
            value = compare_space(profile, answers)
            observed = any(
                value[field] in {"일치", "불일치"}
                for field in ("floor", "area", "kitchen", "ventilation", "water_supply")
            )
            fact_id = register_fact(
                scope,
                industry_code=code,
                source="industry_profile",
                metric="space_fit",
                value=value,
                unit="업종 공간 요건과 임대인 답변의 비교",
                status="observed" if observed else "unknown",
                row_ids=[],
                parent_fact_ids=[profile_id, *answer_ids.values()],
                retain_unknown_value=True,
                comparison={
                    "requirements": profile,
                    "answers": answers,
                    "profile_fact_id": profile_id,
                    "user_fact_ids": answer_ids,
                },
                period="현재 임대인 답변과 업종 공간 요건",
                stores=st,
            )
            st.facts.point_space_fit(scope.request_id, scope.snapshot_id, code, fact_id)
            current[code] = fact_id
        return current
