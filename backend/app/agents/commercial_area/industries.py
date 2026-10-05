"""상권업종분류 중분류 목록을 읽고 씁니다."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from app.industries.catalog import (
    INDUSTRIES,
    INDUSTRY_MAJORS,
    PUBLIC_MIDDLE_TO_INDUSTRY,
    PUBLIC_SMALL_TO_INDUSTRY,
)

from .config import Settings
from .schemas import MiddleCode, Store


def load_middle_master(settings: Settings | None = None) -> list[MiddleCode]:
    """분석은 생성된 공통 카탈로그를 읽습니다."""
    return [
        MiddleCode(
            code=code,
            name=name,
            major_code=INDUSTRY_MAJORS[code][0],
            major_name=INDUSTRY_MAJORS[code][1],
        )
        for code, name in sorted(INDUSTRIES.items())
    ]


def canonicalize_store(store: Store) -> Store:
    """소상공인 원천 분류를 서비스 canonical 업종으로 한 번만 접는다.

    G213/G215처럼 중분류가 분할된 경우에는 소분류가 연결표에 있을 때만
    매핑한다. 알 수 없는 소분류를 어느 한쪽으로 추정하지 않는다.
    """
    industry_code = PUBLIC_SMALL_TO_INDUSTRY.get(store.small_code or "")
    if industry_code is None:
        industry_code = PUBLIC_MIDDLE_TO_INDUSTRY.get(store.middle_code)
    if industry_code is None:
        return store
    major_code, major_name = INDUSTRY_MAJORS[industry_code]
    return replace(
        store,
        major_code=major_code,
        major_name=major_name,
        middle_code=industry_code,
        middle_name=INDUSTRIES[industry_code],
    )


def canonicalize_stores(stores: Sequence[Store]) -> list[Store]:
    """점포 수와 순서를 보존하며 모든 집계 전에 서비스 업종으로 변환한다."""
    return [canonicalize_store(store) for store in stores]


def master_from_stores(stores: Sequence[Store]) -> list[MiddleCode]:
    unique: dict[str, MiddleCode] = {}
    for store in stores:
        if store.middle_code and store.middle_code not in unique:
            unique[store.middle_code] = MiddleCode(
                code=store.middle_code,
                name=store.middle_name,
                major_code=store.major_code,
                major_name=store.major_name,
            )
    return sorted(unique.values(), key=lambda r: r.code)


def write_master(path: Path, rows: Sequence[MiddleCode]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["middle_code", "middle_name", "major_code", "major_name"])
        for row in sorted(rows, key=lambda r: r.code):
            writer.writerow([row.code, row.name, row.major_code, row.major_name])
