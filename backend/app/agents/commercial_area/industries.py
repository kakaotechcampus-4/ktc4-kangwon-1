"""상권업종분류 중분류 목록을 읽고 씁니다."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

from app.industries import MASTER_PATH
from app.industries.catalog import INDUSTRIES, INDUSTRY_MAJORS

from .config import Settings
from .schemas import MiddleCode, Store

REQUIRED_COLUMNS = {"middle_code", "middle_name", "major_code", "major_name"}


def load_middle_master(settings: Settings) -> list[MiddleCode]:
    path = settings.upjong_master_path
    if not path.exists():
        raise ValueError("업종 마스터 파일이 없습니다.")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            raise ValueError("업종 마스터 필수 컬럼이 없습니다.")
        raw_rows = list(reader)
        if not raw_rows or any(
            not all((row.get(field) or "").strip() for field in REQUIRED_COLUMNS)
            for row in raw_rows
        ):
            raise ValueError("업종 마스터가 비어 있거나 필수 값이 없습니다.")
        rows = [
            MiddleCode(
                code=row["middle_code"].strip(),
                name=row["middle_name"].strip(),
                major_code=row["major_code"].strip(),
                major_name=row["major_name"].strip(),
            )
            for row in raw_rows
        ]
    unique: dict[str, MiddleCode] = {}
    for row in rows:
        if row.code in unique:
            raise ValueError("업종 마스터에 중복 코드가 있습니다.")
        unique[row.code] = row
    if path.resolve() == MASTER_PATH.resolve() and (
        set(unique) != set(INDUSTRIES)
        or any(
            row.name != INDUSTRIES[row.code]
            or (row.major_code, row.major_name) != INDUSTRY_MAJORS[row.code]
            for row in rows
        )
    ):
        raise ValueError("운영 업종 마스터가 공통 카탈로그와 다릅니다.")
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
