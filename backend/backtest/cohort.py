"""제공 표의 주소를 로컬 점포 원문과 엄격히 대조해 비용 없는 평가 표본을 만듭니다."""

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from app.db.connection import readonly
from backtest.catalog import develop_code
from backtest.offline import block_network, write_json

ADDRESS = re.compile(
    r"^(?:서울특별시|서울시|서울)\s+(\S+구)\s+(\S+)\s+"
    r"(지하\s*|산\s*)?(\d+(?:\s*-\s*\d+)?)(?=\s|,|\(|$)"
)


def address_key(value: str) -> tuple | None:
    match = ADDRESS.match(str(value or "").strip())
    if match is None:
        return None
    district, name, marker, number = match.groups()
    if name.endswith(("대로", "로", "길")):
        kind = "road"
    elif name.endswith(("동", "가")):
        kind = "parcel"
    else:
        return None
    return kind, district, name, (marker or "").strip(), re.sub(r"\s+", "", number)


def build(source: Path, data: Path, out: Path) -> dict:
    if out.exists():
        raise ValueError("표본 결과 폴더가 이미 있습니다.")
    with source.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or len({row["행"] for row in rows}) != len(rows):
        raise ValueError("비어 있거나 행 ID가 중복된 표본입니다.")
    keys = {key for row in rows if (key := address_key(row["주소"])) is not None}
    found: dict[tuple, dict] = defaultdict(dict)
    with block_network(), readonly(data) as db:
        versions = db.execute(
            "SELECT v.version_id,v.quarter,v.file_hash,f.columns_json "
            "FROM data_versions v JOIN source_fields f USING(version_id) "
            "JOIN release_versions r USING(version_id) WHERE v.source='stores' "
            "AND r.release_id=(SELECT MAX(release_id) FROM data_releases)"
        ).fetchall()
        if len(versions) != 1:
            raise ValueError("고정할 점포 자료 버전이 하나여야 합니다.")
        version = versions[0]
        columns = json.loads(version["columns_json"])
        road = columns.index("도로명주소")
        parcel = columns.index("지번주소")
        query = (
            "SELECT row_key,latitude,longitude,"
            f"json_extract(payload,'$[{road}]'),json_extract(payload,'$[{parcel}]') "
            "FROM stores WHERE version_id=?"
        )
        for row_id, latitude, longitude, road_address, parcel_address in db.execute(
            query, (version["version_id"],)
        ):
            if (
                latitude is None
                or longitude is None
                or not math.isfinite(latitude)
                or not math.isfinite(longitude)
                or not -90 <= latitude <= 90
                or not -180 <= longitude <= 180
            ):
                continue
            for value in (road_address, parcel_address):
                key = address_key(value)
                if key is not None and key in keys:
                    found[key][row_id] = {
                        "latitude": round(latitude, 6),
                        "longitude": round(longitude, 6),
                        "road_address": road_address,
                        "jibun_address": parcel_address,
                    }
    cases, exclusions = [], []
    for row in rows:
        code = develop_code(row["실제 업종"])
        key = address_key(row["주소"])
        candidates = found.get(key, {})
        points = {(item["latitude"], item["longitude"]) for item in candidates.values()}
        reason = (
            "unparsed_address"
            if key is None
            else "unmatched_address"
            if not points
            else "ambiguous_coordinate"
            if len(points) != 1
            else None
        )
        if reason is not None:
            exclusions.append(
                {
                    "id": row["행"],
                    "address": row["주소"],
                    "target_industry_code": code,
                    "reason": reason,
                    "candidate_coordinate_count": len(points),
                }
            )
            continue
        representative = candidates[sorted(candidates)[0]]
        cases.append(
            {
                "id": row["행"],
                "radius_m": 500,
                "target_industry_code": code,
                "site": {"input_address": row["주소"], **representative},
                "coordinate_source": {
                    "version_id": version["version_id"],
                    "address_key": list(key),
                    "row_ids": sorted(candidates),
                    "rounding_decimal_places": 6,
                    "note": "현재 점포의 건물 수준 좌표; 당시 지오코딩·호실 검증 결과는 아님",
                },
            }
        )
    if not cases:
        raise ValueError("좌표를 엄격히 대조할 수 있는 주소가 없습니다.")
    metadata = {
        "kind": "current-data-address-matched-cohort",
        "source": str(source.resolve()),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "matcher_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "store_version": {key: version[key] for key in ("version_id", "quarter", "file_hash")},
        "input_n": len(rows),
        "matched_n": len(cases),
        "excluded_n": len(exclusions),
        "exclusion_counts": dict(Counter(item["reason"] for item in exclusions)),
        "all_industry_counts": dict(Counter(develop_code(row["실제 업종"]) for row in rows)),
        "matched_industry_counts": dict(Counter(case["target_industry_code"] for case in cases)),
        "interpretation": "현재 자료의 제공 업종 일치도 진단; 생존 예측·당시 실험 재현 아님",
        "selection": "성과를 보지 않고 건물 주소와 단일 반올림 좌표 일치로 포함 여부 결정",
    }
    out.mkdir(parents=True)
    write_json(out / "sites.json", {"sites": cases})
    write_json(out / "cohort.json", {"metadata": metadata, "exclusions": exclusions})
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="현재 로컬 점포 자료로 평가 주소의 좌표를 대조합니다."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.source, args.data, args.out), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
