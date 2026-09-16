"""공통 업종 어휘의 값 객체."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Industry:
    """소상공인 상권업종 중분류 하나.

    `app/schemas.py`의 `Category(major, middle)` 두 칸에 그대로 들어간다 —
    `major_name`이 `category.major`, `name`이 `category.middle`이다.
    """

    code: str
    name: str
    major_code: str
    major_name: str
    has_seoul: bool = False
    note: str = ""
