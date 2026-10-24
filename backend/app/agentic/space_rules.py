"""확인 화면 공간 값과 업종 요건으로 제외·순위 조정·안내를 정합니다."""

import csv
from dataclasses import dataclass
from functools import cache

from app.industries import DATA_DIR

from .space_values import GROUND_LEVELS, area_fit, floor_number

FACILITY_NAMES = {"kitchen": "주방", "ventilation": "배기(덕트)", "water_supply": "급배수"}
FACILITY_STATES = frozenset({"present", "installable", "unavailable"})
FACILITY_STATE_TEXT = {"present": "있음", "installable": "설치 가능", "unavailable": "설치 불가"}
ACTIVE_LEVELS = frozenset({"required", "preferred", "conditional"})


@dataclass(frozen=True)
class SpaceJudgement:
    excluded: bool
    exclusion_reasons: tuple[str, ...]
    adjustment: int
    notes: tuple[str, ...]


@cache
def load_requirements() -> dict[str, dict]:
    path = DATA_DIR / "industry_space_requirements.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["industry_code"]: row for row in csv.DictReader(handle)}


def _ground_penalty(floor: int) -> int:
    if floor == 2:
        return -5
    if floor == 3:
        return -7
    if floor == -1:
        return -3
    return -10


def judge(profile: dict, answers: dict) -> SpaceJudgement:
    reasons: list[str] = []
    notes: list[str] = []
    adjustment = 0
    confirmed = answers.get("confirmed_facilities")
    states = confirmed if isinstance(confirmed, dict) else {}
    for field, name in FACILITY_NAMES.items():
        level = profile.get(field + "_needed")
        if level not in ACTIVE_LEVELS:
            continue
        state = states.get(field)
        if state not in FACILITY_STATES:
            notes.append(f"{name} 확인 필요")
        elif state == "unavailable":
            if level == "required":
                reasons.append(f"{name} 설치 불가")
            elif level == "preferred":
                adjustment -= 5
            else:
                notes.append(f"{name} 설치 불가: 메뉴·작업 방식 확인 필요")
        elif state == "installable" and level == "required":
            notes.append(f"{name} 설치 공사 필요")
    floor = floor_number(answers.get("floor"))
    floor_level = profile.get("floor_preference")
    if floor_level in GROUND_LEVELS:
        if floor is None:
            notes.append("층 확인 필요")
        elif floor != 1:
            if floor_level == "ground_required":
                reasons.append("1층이 아님")
            else:
                adjustment += _ground_penalty(floor)
    elif floor_level == "basement_preferred" and floor is not None and floor < 0:
        adjustment += 3
    area = answers.get("exclusive_area")
    if area is not None and area_fit(profile.get("area_band"), area) == "불일치":
        notes.append(f"면적이 업종 일반 범위({profile.get('area_band')}) 밖")
    return SpaceJudgement(bool(reasons), tuple(reasons), adjustment, tuple(notes))
