"""상권업종분류 중분류 목록을 읽고 씁니다."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from app.industries.catalog import (
    EXCLUDED_SMALLS,
    INDUSTRIES,
    INDUSTRY_MAJORS,
    INDUSTRY_SOURCE_MIDDLES,
    SPLIT_MIDDLES,
)
from app.industries.lookup import service_code

from .config import Settings
from .schemas import MiddleCode, Store


def map_stores(stores: Sequence[Store], master: Sequence[MiddleCode] | None = None) -> list[Store]:
    """모든 집계의 입력을 같은 소분류 우선 서비스 업종으로 변환합니다."""
    custom = {m.code: m for m in master or () if m.code not in INDUSTRIES}
    mapped = []
    for store in stores:
        code = service_code(store.middle_code, store.small_code)
        if code:
            major, major_name = INDUSTRY_MAJORS[code]
            mapped.append(
                replace(
                    store,
                    middle_code=code,
                    middle_name=INDUSTRIES[code],
                    major_code=major,
                    major_name=major_name,
                )
            )
        elif store.middle_code in custom:
            mapped.append(store)
    return mapped


def incomplete_split_codes(stores: Sequence[Store]) -> set[str]:
    """분할 근거가 없는 중분류는 해당 서비스 업종의 LQ를 차단합니다."""

    missing = {
        s.middle_code
        for s in stores
        if s.middle_code in SPLIT_MIDDLES
        and service_code(s.middle_code, s.small_code) is None
        and s.small_code not in EXCLUDED_SMALLS
    }
    return {
        code for code, sources in INDUSTRY_SOURCE_MIDDLES.items() if missing.intersection(sources)
    }


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
