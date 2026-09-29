"""상권업종분류 중분류 목록을 읽고 씁니다."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

from app.industries.catalog import INDUSTRIES, INDUSTRY_MAJORS

from .config import Settings
from .schemas import MiddleCode, Store

REQUIRED_COLUMNS = {"middle_code", "middle_name", "major_code", "major_name"}


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
