import re

from app.domain.space_values import (
    CONFIRMED_STATES,
    GROUND_LEVELS,
    NEEDED_LEVELS,
    area_fit,
    floor_number,
    readable_answer,
)

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


def chosen_answer(metric, rows):
    return next((row for row in rows if readable_answer(metric, row[1])), rows[0])
