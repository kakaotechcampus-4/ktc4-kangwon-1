"""업종 공간 요건을 명시된 임대인 답변과만 대조합니다."""

import json
import re
from contextlib import nullcontext

from app.db.connection import connect
from app.industries.catalog import INDUSTRIES

from .facts import register_fact
from .space_values import (
    CONFIRMED_STATES,
    GROUND_LEVELS,
    NEEDED_LEVELS,
    area_fit,
    floor_number,
    readable_answer,
)

CONFIRMED_UNIT = "확인 화면 확정값"

_FACILITY = re.compile(
    r"(?P<names>(?:주방|배기|후드|급배수)(?:\s*(?:·|/|및|와)\s*(?:주방|배기|후드|급배수))*)"
    r"\s*(?:설비|시설)?\s*(?:은|는|이|가)?\s*[:=]?\s*"
    r"(?P<state>있음|없음|있다|없다|있습니다|없습니다|있어요|없어요|true|false|O|X)"
    r"\s*(?=$|[,;\n])",
    re.IGNORECASE,
)


def _facilities(answers):
    found = {"kitchen": set(), "ventilation": set(), "water_supply": set()}
    names = {
        "주방": "kitchen",
        "배기": "ventilation",
        "후드": "ventilation",
        "급배수": "water_supply",
    }
    for field in ("existing_facilities", "space_condition"):
        answer = answers.get(field)
        if not isinstance(answer, str):
            continue
        # shortcut: 명시된 설비 유무만 비교하며, 구조화된 답변 계약이 생기면 교체합니다.
        for match in _FACILITY.finditer(answer):
            present = match["state"].casefold() in {
                "있음",
                "있다",
                "있습니다",
                "있어요",
                "true",
                "o",
            }
            for label in re.findall(r"주방|배기|후드|급배수", match["names"]):
                found[names[label]].add(present)
    return {key: next(iter(values)) if len(values) == 1 else None for key, values in found.items()}


def compare_space(profile, answers):
    """설명 문장에서 면적 기준이나 급배수 요건을 새로 추론하지 않습니다."""
    result = {
        "floor": "미확인",
        "area": area_fit(profile.get("area_band"), answers.get("exclusive_area")),
    }
    preference = profile.get("floor_preference")
    expected_floor = 1 if preference in GROUND_LEVELS else floor_number(preference, preference=True)
    actual_floor = floor_number(answers.get("floor"))
    if preference in (False, "false", "basement_preferred"):
        result["floor"] = "해당 없음"
    elif expected_floor is not None and actual_floor is not None:
        result["floor"] = "일치" if expected_floor == actual_floor else "불일치"
    facilities = _facilities(answers)
    confirmed = answers.get("confirmed_facilities")
    if isinstance(confirmed, dict):
        for field, state in confirmed.items():
            if field in facilities:
                facilities[field] = CONFIRMED_STATES.get(state)
    for field in ("kitchen", "ventilation", "water_supply"):
        requirement = profile.get(field + "_needed")
        result[field] = "미확인"
        if requirement in (False, "false"):
            result[field] = "해당 없음"
        elif requirement in NEEDED_LEVELS and facilities[field] is not None:
            result[field] = "일치" if facilities[field] else "불일치"
    result["reviewed"] = profile.get("reviewed", False) in (True, "true")
    result["confidence"] = profile.get("confidence", "low")
    return result


def confirmed_answers(scope, *, connection=None):
    with connect(scope.path) if connection is None else nullcontext(connection) as db:
        rows = db.execute(
            "SELECT metric,value_json FROM facts WHERE request_id=? AND snapshot_id=? "
            "AND source='user' AND status='observed' AND citable=1 AND unit=? "
            "AND metric IN ('floor','exclusive_area','existing_facilities') "
            "ORDER BY created_at DESC,fact_id DESC",
            (scope.request_id, scope.snapshot_id, CONFIRMED_UNIT),
        ).fetchall()
    answers = {}
    for metric, raw in rows:
        value = json.loads(raw)
        if metric == "existing_facilities":
            if isinstance(value, dict):
                answers.setdefault("confirmed_facilities", value)
        else:
            answers.setdefault(metric, value)
    return answers


def ensure_space_fits(scope, *, connection=None):
    """비교 값·부모 계보가 바뀌면 새 fact를 만들고 현재 포인터만 갱신합니다."""
    with connect(scope.path) if connection is None else nullcontext(connection) as db:
        if not db.in_transaction:
            db.execute("BEGIN IMMEDIATE")
        profiles, answers, answer_ids, candidates = {}, {}, {}, {}
        for row in db.execute(
            "SELECT fact_id,industry_code,source,metric,value_json FROM facts "
            "WHERE request_id=? AND snapshot_id=? AND status='observed' AND citable=1 "
            "AND (metric='space_requirements' OR source='user') "
            "ORDER BY created_at DESC,fact_id DESC",
            (scope.request_id, scope.snapshot_id),
        ):
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
                chosen = next((c for c in rows if readable_answer(metric, c[1])), rows[0])
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
                connection=db,
            )
            db.execute(
                "INSERT INTO space_fit_current VALUES(?,?,?,?) "
                "ON CONFLICT(request_id,snapshot_id,industry_code) DO UPDATE "
                "SET fact_id=excluded.fact_id WHERE fact_id!=excluded.fact_id",
                (scope.request_id, scope.snapshot_id, code, fact_id),
            )
            current[code] = fact_id
        return current
