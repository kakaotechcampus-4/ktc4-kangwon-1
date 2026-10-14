"""기존 파서를 사용하는 파일/API 적재와 페이지 체크포인트입니다."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import math
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any

from app.agents.business_lifecycle.area_resolver import load_shape_features, required_shape_paths
from app.agents.business_lifecycle.client import normalize_row
from app.agents.commercial_area.client import to_store
from app.agents.commercial_area.industries import incomplete_split_codes, map_stores
from app.agents.floating_population.models import FlpopRecord, PopulationRecord
from app.local_data.database import DataValidationError, LocalDataDB


def require(row: dict, fields: Iterable[str]) -> None:
    missing = [key for key in fields if row.get(key) is None or str(row[key]).strip() == ""]
    if missing:
        raise DataValidationError("필수 필드 결측: " + ",".join(missing))


def normalize(source: str, row: dict, quarter: str) -> dict:
    """원문은 보존하고 기존 파서로 검증한 검색용 키만 추출합니다."""
    require(row, ("STDR_YYQU_CD", "TRDAR_CD"))
    if str(row["STDR_YYQU_CD"]) != quarter:
        raise DataValidationError("요청 분기와 다른 행")
    area = str(row["TRDAR_CD"])
    industry = None
    if source == "lifecycle":
        parsed = normalize_row(row)
        require(parsed, parsed.keys())
        industry = str(parsed["svc_induty_cd"])
        for key in (
            "similr_induty_stor_co",
            "stor_co",
            "frc_stor_co",
            "opbiz_rt",
            "opbiz_stor_co",
            "clsbiz_rt",
            "clsbiz_stor_co",
        ):
            value = float(parsed[key])
            if not math.isfinite(value) or value < 0:
                raise DataValidationError("잘못된 개폐업 숫자")
    elif source == "floating":
        parsed_float = FlpopRecord.from_api_row(row)
        values = [
            parsed_float.total,
            parsed_float.male,
            parsed_float.female,
            *parsed_float.by_time.values(),
            *parsed_float.by_day.values(),
            *parsed_float.by_age.values(),
        ]
        if any(v is None or not math.isfinite(v) or v < 0 for v in values):
            raise DataValidationError("유동 필수 숫자 결측/오류")
    elif source in ("resident", "worker"):
        kind = "REPOP" if source == "resident" else "WRC_POPLTN"
        require(row, PopulationRecord.columns(kind))
        parsed_population = PopulationRecord.from_api_row(row, kind)
        values = [parsed_population.total, *parsed_population.by_age.values()]
        if source == "resident":
            values.append(parsed_population.households)
        if any(v is None or not math.isfinite(v) or v < 0 for v in values):
            raise DataValidationError("인구 숫자 오류")
    else:
        raise DataValidationError("지원하지 않는 행 원천")
    return {
        "row_key": area + (":" + industry if industry else ""),
        "area_code": area,
        "industry_code": industry,
        "payload": row,
    }


def file_hash(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def csv_rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def store_rows(path: Path, fields: dict[str, str]):
    for original in csv_rows(path):
        require(
            original,
            (
                "시도명",
                *(
                    fields[k]
                    for k in (
                        "bizesId",
                        "indsLclsCd",
                        "indsMclsCd",
                        "indsSclsCd",
                        "lat",
                        "lon",
                        "signguCd",
                    )
                ),
            ),
        )
        if original["시도명"] != "서울특별시":
            continue
        store = to_store({key: original[column] for key, column in fields.items()})
        if (
            store is None
            or store.latitude is None
            or store.longitude is None
            or not math.isfinite(store.latitude)
            or not math.isfinite(store.longitude)
            or not 37 <= store.latitude <= 38
            or not 126 <= store.longitude <= 128
        ):
            raise DataValidationError("점포 좌표/필수 필드 오류")
        mapped = map_stores([store])
        if not mapped and incomplete_split_codes([store]):
            raise DataValidationError("분할 업종의 소분류 매핑 근거가 없습니다.")
        yield {
            "row_key": store.store_id,
            "industry_code": mapped[0].middle_code if mapped else None,
            "district_code": store.district_code,
            "latitude": store.latitude,
            "longitude": store.longitude,
            "payload": original,
        }


def shape_rows(path: Path):
    for feature in load_shape_features(path):
        row: dict[str, Any] = dict(feature.attributes)
        require(row, ("TRDAR_CD",))
        row["bbox"] = feature.bbox
        row["rings"] = feature.rings
        row["crs"] = "EPSG:5181"
        yield {"row_key": row["TRDAR_CD"], "area_code": row["TRDAR_CD"], "payload": row}


def shape_hash(path: Path) -> str:
    paths = required_shape_paths(path)
    if path.with_suffix(".cpg").exists():
        paths.append(path.with_suffix(".cpg"))
    return file_hash(paths)


def rows_hash(rows: list[dict]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(
            json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        )
        digest.update(b"\n")
    return digest.hexdigest()


async def collect_pages(
    db: LocalDataDB, key: str, fetch: Callable[[int, int], Awaitable[dict]]
) -> tuple[list[dict], int]:
    """완료된 페이지는 재사용. 동시 네 페이지가 모두 끝난 뒤 오류를 전파합니다."""
    requests = 0

    async def page(start: int, expected_total: int | None = None) -> dict:
        nonlocal requests
        body = await asyncio.to_thread(db.page, key, start)
        cached = body is not None
        if body is None:
            await asyncio.to_thread(db.reserve_http)
            requests += 1
            body = await fetch(start, start + 999)
        total = int(body.get("list_total_count", 0))
        if expected_total is not None and total != expected_total:
            raise DataValidationError("이어 받는 중 총행 수 변경: 체크포인트 재수집 필요")
        rows = body.get("row", [])
        if not isinstance(rows, list) or len(rows) != min(1000, max(0, total - start + 1)):
            raise DataValidationError("페이지 행 수 누락")
        if not cached:
            await asyncio.to_thread(db.save_page, key, start, body)
        return body

    first = await page(1)
    total = int(first.get("list_total_count", 0))
    rows = list(first.get("row", []))
    starts = list(range(1001, total + 1, 1000))
    for offset in range(0, len(starts), 4):
        results = await asyncio.gather(
            *(page(start, total) for start in starts[offset : offset + 4]),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
            rows.extend(result.get("row", []))
    if not rows:
        raise DataValidationError("API 전체 자료가 비었습니다.")
    return rows, requests
