"""상권업종분류 중분류 목록을 읽고 씁니다."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

from .config import Settings
from .schemas import MiddleCode, Store

REQUIRED_COLUMNS = {"middle_code", "middle_name", "major_code", "major_name"}


def load_middle_master(settings: Settings) -> list[MiddleCode]:
    path = settings.upjong_master_path
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            return []
        rows = [
            MiddleCode(
                code=row["middle_code"].strip(),
                name=row["middle_name"].strip(),
                major_code=row["major_code"].strip(),
                major_name=row["major_name"].strip(),
            )
            for row in reader
            if row.get("middle_code")
        ]
    unique: dict[str, MiddleCode] = {}
    for row in rows:
        unique.setdefault(row.code, row)
    return sorted(unique.values(), key=lambda r: r.code)


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
