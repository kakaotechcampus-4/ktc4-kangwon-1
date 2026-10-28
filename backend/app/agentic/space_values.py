"""업종 공간 요건과 임대인 답변을 DB 없이 해석합니다."""

import math
import re

FACILITY_LEVELS = frozenset({"required", "preferred", "conditional", "false"})
FLOOR_LEVELS = frozenset({"ground_required", "ground_preferred", "basement_preferred", "false"})
GROUND_LEVELS = frozenset({"ground_required", "ground_preferred"})
NEEDED_LEVELS = frozenset({True, "true", "required", "preferred"})
CONFIRMED_STATES = {"present": True, "unavailable": False, "installable": None}

_AREA = re.compile(r"(?:약\s*)?(\d+(?:\.\d+)?)\s*(㎡|m2|m²|평)")
_AREA_ANSWER = re.compile(rf"{_AREA.pattern}(?:\s*\(\s*{_AREA.pattern}\s*\))?")
_AREA_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*[~-]\s*(\d+(?:\.\d+)?)\s*(㎡|m2|m²|평)")


def floor_number(value, *, preference=False):
    if not isinstance(value, str):
        return None
    suffix = r"(?:\s+접근 우선 가정)?" if preference else ""
    match = re.fullmatch(
        r"\s*(지하|지상|지|B)?\s*0*([1-9][0-9]*)"
        r"(?:\s*(층|F)(?:\s*[0-9]+\s*호)?|\s+[0-9]+\s*호)?" + suffix + r"\s*",
        value,
        flags=re.IGNORECASE,
    )
    # 호수·추측 문장에서 숫자만 뽑지 않고, 층 접두어나 단위가 명시된 값만 비교합니다.
    if match is None or not (match[1] or match[3]):
        return None
    basement = (match[1] or "").casefold() in {"지하", "지", "b"}
    return int(match[2]) * (-1 if basement else 1)


def area_fit(requirement, answer):
    if requirement in (False, "false"):
        return "해당 없음"
    if not isinstance(requirement, str) or not isinstance(answer, str):
        return "미확인"
    observed = _AREA_ANSWER.fullmatch(answer.strip())
    bounds = _AREA_RANGE.fullmatch(requirement.strip())
    if not observed or not bounds:
        return "미확인"
    expected_factor = 400 / 121 if bounds[3] == "평" else 1
    actual_factor = 400 / 121 if observed[2] == "평" else 1
    low, high = float(bounds[1]) * expected_factor, float(bounds[2]) * expected_factor
    value = float(observed[1]) * actual_factor
    if (
        not all(math.isfinite(v) for v in (low, high, value))
        or low <= 0
        or high < low
        or value <= 0
    ):
        return "미확인"
    if observed[3] is not None:
        second_factor = 400 / 121 if observed[4] == "평" else 1
        second = float(observed[3]) * second_factor
        # 병기 단위는 각 표기 자릿수의 반올림 범위가 겹칠 때만 같은 면적으로 봅니다.
        rounding = sum(
            factor * 0.5 * 10 ** (-len(number.partition(".")[2]))
            for number, factor in ((observed[1], actual_factor), (observed[3], second_factor))
        )
        if not math.isfinite(second) or second <= 0 or abs(value - second) > rounding:
            return "미확인"
    return "일치" if low <= value <= high else "불일치"


def readable_answer(metric, value):
    if metric == "floor":
        return floor_number(value) is not None
    if not isinstance(value, str):
        return False
    return bool(_AREA_ANSWER.fullmatch(value.strip()))
