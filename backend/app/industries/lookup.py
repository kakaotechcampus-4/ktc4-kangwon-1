"""업종 조회와 이름 정규화.

`catalog.py`가 원본 표라면 여기는 그 표를 쓰는 방법이다. 판단이 들어가는 건 전부 여기 있다.

이름 정규화가 이 모듈의 존재 이유다. 지금 팀 안에서 같은 한식이 `한식음식점`(개폐업) /
`한식 음식점업`(경쟁업체) / `중식`(결정 실제 출력)으로 갈려 있는데, `app/schemas.py`의 중복 검사는
casefold만 해서 이 셋을 서로 다른 업종으로 통과시킨다. `find_by_name()`이 그걸 합친다.
"""

from __future__ import annotations

import re

from .catalog import (
    INDUSTRIES,
    INDUSTRY_MAJORS,
    LEGACY70_TO_INDUSTRY,
    SEOUL_TO_INDUSTRY,
)
from .models import Industry

_TAIL = re.compile(r"(소매업|판매업|운영업|서비스업|전문점|판매|소매|업소|업|점)$")
_NOISE = re.compile(r"[\s\-,·ㆍ/()]|및")


def normalize_name(name: str) -> str:
    """비교용으로만 쓰는 축약형. 화면에 내보내면 안 된다.

    `한식 음식점업` · `한식음식점` → 둘 다 `한식음식`
    """
    text = _NOISE.sub("", name or "")
    for _ in range(2):
        text = _TAIL.sub("", text)
    return text


_BY_NORMALIZED: dict[str, str] = {}
for _code, _name in INDUSTRIES.items():
    _BY_NORMALIZED.setdefault(normalize_name(_name), _code)


def get(code: str) -> Industry:
    """중분류 코드로 업종을 찾는다. 없으면 KeyError."""
    name = INDUSTRIES[code]
    major_code, major_name = INDUSTRY_MAJORS[code]
    return Industry(code=code, name=name, major_code=major_code, major_name=major_name)


def find(code: str) -> Industry | None:
    return get(code) if code in INDUSTRIES else None


def find_by_name(name: str) -> Industry | None:
    """표기가 달라도 같은 업종으로 찾아준다. 결정 에이전트 응답을 검사할 때 쓴다."""
    code = _BY_NORMALIZED.get(normalize_name(name))
    return get(code) if code else None


def from_seoul(seoul_code: str) -> Industry | None:
    """서울시 생활밀접업종 코드(`CS100001`)를 우리 업종으로. 제외된 코드는 None."""
    code = SEOUL_TO_INDUSTRY.get(seoul_code)
    return get(code) if code else None


def from_legacy70(legacy_id: int) -> tuple[Industry, ...]:
    """개폐업 70업종 ID를 우리 업종으로.

    **여럿이 돌아올 수 있다.** 개폐업 하나가 우리 중분류 여럿으로 갈라지는 경우가 8건 있다
    (예: 33 자동차·모터사이클·부품 → G202 · G203 · G222). 개폐업이 주는 값은 개수가 아니라
    0~100 점수라 **여기 나온 업종들에 그대로 복제하면 안 된다.** 가중 방식은 팀 미합의 사항이다.
    """
    return tuple(get(code) for code in LEGACY70_TO_INDUSTRY.get(legacy_id, ()))


def as_category(code: str) -> tuple[str, str]:
    """`app.schemas.Category(major=..., middle=...)` 에 넣을 두 값."""
    industry = get(code)
    return industry.major_name, industry.name
