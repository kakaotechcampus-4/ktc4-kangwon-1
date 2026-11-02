"""고정된 로컬 자료를 읽기 전용으로 조회하고 기존 표본과 겹치는 지역을 제외합니다."""

import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from app.db.connection import readonly
from app.geo import to_epsg5181
from app.industries.catalog import EXCLUDED_SEOUL_INDUSTRIES, INDUSTRY_TO_SEOUL, SEOUL_TO_INDUSTRY
from backtest.cohort import address_key


def inventory(path: Path) -> list[dict]:
    with readonly(path) as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT v.*,f.columns_json FROM data_versions v "
                "JOIN source_fields f USING(version_id) "
                "JOIN release_versions r USING(version_id) "
                "WHERE r.release_id=(SELECT MAX(release_id) FROM data_releases) "
                "ORDER BY v.source,v.quarter"
            )
        ]


def one_version(versions: list[dict], source: str, quarter="") -> dict:
    selected = [v for v in versions if v["source"] == source and v["quarter"] == quarter]
    if len(selected) != 1:
        raise ValueError("원천·분기마다 고정할 자료 버전이 하나여야 합니다.")
    return selected[0]


def load_areas(path: Path, version: dict) -> dict:
    columns = json.loads(version["columns_json"])
    with readonly(path) as db:
        areas = {}
        for row in db.execute(
            "SELECT area_code,payload FROM areas WHERE version_id=?", (version["version_id"],)
        ):
            raw = dict(zip(columns, json.loads(row["payload"]), strict=True))
            if raw.get("crs") != "EPSG:5181":
                raise ValueError("공간 제외에 필요한 상권 좌표계가 다릅니다.")
            bbox = raw.get("bbox", [])
            if (
                len(bbox) != 4
                or not all(math.isfinite(v) for v in bbox)
                or bbox[0] > bbox[2]
                or bbox[1] > bbox[3]
            ):
                raise ValueError("상권 공간 범위를 검증할 수 없습니다.")
            areas[row["area_code"]] = {
                "area": row["area_code"],
                "name": raw.get("TRDAR_CD_N"),
                "district": str(raw["SIGNGU_CD"]),
                "district_name": raw["SIGNGU_CD_"],
                "kind": raw["TRDAR_SE_C"],
                "bbox": bbox,
            }
    return areas


def resolve_originals(path: Path, version: dict, metadata: dict, areas: dict) -> dict:
    source = Path(metadata["source"])
    if hashlib.sha256(source.read_bytes()).hexdigest() != metadata["source_sha256"]:
        raise ValueError("기존 245개 표본의 주소 원본이 달라졌습니다.")
    with source.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != metadata["input_n"]:
        raise ValueError("기존 표본의 주소 수가 다릅니다.")
    keys = {address_key(row["주소"]) for row in rows}
    if None in keys:
        raise ValueError("기존 주소의 구와 건물 위치를 해석할 수 없습니다.")
    found = defaultdict(set)
    columns = json.loads(version["columns_json"])
    road, parcel = columns.index("도로명주소"), columns.index("지번주소")
    with readonly(path) as db:
        for lat, lon, road_address, parcel_address in db.execute(
            "SELECT latitude,longitude,json_extract(payload,?),json_extract(payload,?) "
            "FROM stores WHERE version_id=?",
            (f"$[{road}]", f"$[{parcel}]", version["version_id"]),
        ):
            if lat is None or lon is None or not math.isfinite(lat) or not math.isfinite(lon):
                continue
            for address in (road_address, parcel_address):
                key = address_key(address)
                if key in keys:
                    found[key].add((round(lat, 6), round(lon, 6)))
    districts = {v["district_name"]: v["district"] for v in areas.values()}
    unknown_districts, points, matches = set(), set(), []
    for row in rows:
        key = address_key(row["주소"])
        coordinates = found[key]
        if key[1] not in districts:
            raise ValueError("기존 주소의 구를 현재 지도와 연결할 수 없습니다.")
        if not coordinates:
            # 위치를 모르는 기존 주소가 새 검증에 섞이지 않게 해당 구 전체를 제외합니다.
            unknown_districts.add(districts[key[1]])
        points.update(coordinates)
        matches.append(
            {"id": row["행"], "district": districts[key[1]], "coordinate_n": len(coordinates)}
        )
    return {
        "source_sha256": metadata["source_sha256"],
        "input_n": len(rows),
        "matched_n": sum(bool(v["coordinate_n"]) for v in matches),
        "unlocated_n": sum(not v["coordinate_n"] for v in matches),
        "unlocated_districts": sorted(unknown_districts),
        "matches": matches,
        "coordinates": [list(v) for v in sorted(points)],
        "projected_points": [list(to_epsg5181(*v)) for v in sorted(points)],
    }


def bbox_near(bbox: list[float], point: list[float], buffer_m=1000) -> bool:
    x, y = point
    dx = max(bbox[0] - x, 0, x - bbox[2])
    dy = max(bbox[1] - y, 0, y - bbox[3])
    return math.hypot(dx, dy) <= buffer_m


def split_areas(
    areas: dict, originals: dict, blocked_codes: set[str], *, seed=20261026, held_district_n=5
) -> dict:
    districts = sorted(
        {a["district"] for a in areas.values() if a["kind"] == "A"}
        - set(originals["unlocated_districts"])
    )
    if len(districts) < held_district_n:
        raise ValueError("기존 주소와 구를 분리할 검증 지역이 부족합니다.")
    held = sorted(
        sorted(
            districts, key=lambda d: hashlib.sha256(f"{seed}|district|{d}".encode()).hexdigest()
        )[:held_district_n]
    )
    reference, eligible, exclusions = [], [], []
    for code, area in sorted(areas.items()):
        if area["kind"] != "A":
            continue
        if area["district"] not in held:
            reference.append(code)
        elif code in blocked_codes or any(
            bbox_near(area["bbox"], p) for p in originals["projected_points"]
        ):
            exclusions.append(code)
        else:
            eligible.append(code)
    return {
        "held_districts": held,
        "reference_areas": reference,
        "candidate_areas": eligible,
        "spatial_excluded_areas": exclusions,
        "buffer_m": 1000,
        "area_kind": "A",
        "interpretation": "현행 지도는 공간 제외에 사용. 비교 기준은 다른 구의 과거 자료로 계산",
    }


def load_panel(
    path: Path, versions: list[dict], quarters: list[str], area_ids: set[str]
) -> tuple[dict, dict]:
    if not quarters or len(set(quarters)) != len(quarters) or quarters != sorted(quarters):
        raise ValueError("조회 분기는 중복 없이 시간순이어야 합니다.")
    accumulated, row_n = {}, 0
    source_keys = set()
    with readonly(path) as db:
        for quarter in quarters:
            version = one_version(versions, "lifecycle", quarter)
            columns = json.loads(version["columns_json"])
            fields = [
                columns.index(n)
                for n in (
                    "STDR_YYQU_CD",
                    "SIMILR_INDUTY_STOR_CO",
                    "OPBIZ_STOR_CO",
                    "CLSBIZ_STOR_CO",
                )
            ]
            query = (
                "SELECT area_code,industry_code,"
                + ",".join(f"json_extract(payload,'$[{i}]')" for i in fields)
                + " FROM lifecycle WHERE version_id=?"
            )
            for area, source, payload_quarter, stores, opened, closed in db.execute(
                query, (version["version_id"],)
            ):
                if str(payload_quarter) != quarter:
                    raise ValueError("원자료 분기와 버전 분기가 다릅니다.")
                if area not in area_ids:
                    continue
                if source in EXCLUDED_SEOUL_INDUSTRIES:
                    continue
                if source not in SEOUL_TO_INDUSTRY:
                    raise ValueError("서울 업종 대응표에 없는 원자료 코드가 있습니다.")
                key = (area, quarter, source)
                if key in source_keys:
                    raise ValueError("같은 상권·분기·원천 업종이 중복됩니다.")
                source_keys.add(key)
                counts = (stores, opened, closed)
                if any(
                    type(v) not in (int, float)
                    or not math.isfinite(v)
                    or v < 0
                    or not float(v).is_integer()
                    for v in counts
                ):
                    raise ValueError("관측 건수는 결측 없는 음이 아닌 정수여야 합니다.")
                code = SEOUL_TO_INDUSTRY[source]
                bucket = accumulated.setdefault(
                    (area, code, quarter), {"sources": set(), "counts": [0, 0, 0]}
                )
                bucket["sources"].add(source)
                bucket["counts"] = [
                    a + int(b) for a, b in zip(bucket["counts"], counts, strict=True)
                ]
                row_n += 1
    panel, missing = {}, 0
    for area in sorted(area_ids):
        panel[area] = {}
        for code, expected in INDUSTRY_TO_SEOUL.items():
            series = []
            for quarter in quarters:
                bucket = accumulated.get((area, code, quarter))
                value = (
                    tuple(bucket["counts"])
                    if bucket and bucket["sources"] == set(expected)
                    else None
                )
                series.append(value)
                missing += value is None
            panel[area][code] = series
    return panel, {
        "quarters": quarters,
        "raw_observed_rows": row_n,
        "incomplete_service_quarter_cells": missing,
        "missing_rows_filled_with_zero": 0,
        "versions": [
            {
                k: one_version(versions, "lifecycle", q)[k]
                for k in ("version_id", "quarter", "file_hash", "row_count")
            }
            for q in quarters
        ],
    }
