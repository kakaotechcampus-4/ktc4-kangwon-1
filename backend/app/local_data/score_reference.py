"""고정한 점포·상권 버전에서 라벨 없는 C1 참고 분포를 만듭니다. 호출자는 스레드로 격리합니다."""

import json
import math
import threading
from collections import Counter, defaultdict
from functools import lru_cache
from itertools import product
from pathlib import Path
from uuid import uuid4

from app.canonical import canonical_hash, canonical_json, file_sha256
from app.config import BACKEND_DIR
from app.db.connection import readonly
from app.geo import haversine_m, to_epsg5181
from app.industries.catalog import INDUSTRIES

CACHE_DIR = BACKEND_DIR / "cache" / "s2-half-reference"
_BUILDING = threading.Lock()


def inverse_center(x, y):
    """기존 build_density_baseline의 중심점·1cm 수렴 규칙을 그대로 사용합니다."""
    lat, lon = 37.5, 127.0
    for _ in range(12):
        gx, gy = to_epsg5181(lat, lon)
        dx, dy = x - gx, y - gy
        if abs(dx) < 0.01 and abs(dy) < 0.01:
            break
        lat += dy / 111320
        lon += dx / (111320 * math.cos(math.radians(lat)))
    return lat, lon


def _build_reference(path, stores_id, areas_id):
    """반경은 정확한 구면 거리로 재확인하고 격자는 탐색 후보만 줄입니다."""
    with readonly(path) as db:
        fields = db.execute(
            "SELECT columns_json FROM source_fields WHERE version_id=?", (areas_id,)
        ).fetchone()
        columns = json.loads(fields[0])
        areas = [
            dict(zip(columns, json.loads(row[0]), strict=True))
            for row in db.execute("SELECT payload FROM areas WHERE version_id=?", (areas_id,))
        ]
        grid = defaultdict(list)
        for row in db.execute(
            "SELECT latitude,longitude,industry_code FROM stores WHERE version_id=? "
            "AND latitude IS NOT NULL AND longitude IS NOT NULL",
            (stores_id,),
        ):
            lat, lon, code = row
            if code in INDUSTRIES and math.isfinite(lat) and math.isfinite(lon):
                grid[math.floor(lat / 0.005), math.floor(lon / 0.005)].append((lat, lon, code))
        medical = []
        store_fields = json.loads(
            db.execute(
                "SELECT columns_json FROM source_fields WHERE version_id=?", (stores_id,)
            ).fetchone()[0]
        )
        if "표준산업분류코드" in store_fields:
            index = store_fields.index("표준산업분류코드")
            medical = [
                (row[0], row[1])
                for row in db.execute(
                    "SELECT latitude,longitude FROM stores WHERE version_id=? "
                    "AND latitude IS NOT NULL AND longitude IS NOT NULL AND "
                    f"(json_extract(payload,'$[{index}]') GLOB 'Q861*' "
                    f"OR json_extract(payload,'$[{index}]') GLOB 'Q862*')",
                    (stores_id,),
                )
                if math.isfinite(row[0]) and math.isfinite(row[1])
            ]
    samples = []
    for area in areas:
        x, y = (
            area.get("XCNTS_VALUE", area.get("XCNTS_VALU")),
            area.get("YDNTS_VALUE", area.get("YDNTS_VALU")),
        )
        if x is None or y is None:
            continue
        lat, lon = inverse_center(float(x), float(y))
        gx, gy = math.floor(lat / 0.005), math.floor(lon / 0.005)
        counts = Counter(
            code
            for dx, dy in product(range(-2, 3), repeat=2)
            for slat, slon, code in grid.get((gx + dx, gy + dy), [])
            if haversine_m(lat, lon, slat, slon) <= 500
        )
        samples.append(
            {
                "area": str(area["TRDAR_CD"]),
                "latitude": lat,
                "longitude": lon,
                "counts": {code: counts[code] for code in INDUSTRIES},
            }
        )
    return samples, medical


@lru_cache(maxsize=2)
def city_reference(path, stores_id, areas_id, stores_hash, areas_hash):
    """새 자료 버전에서 한 번 계산하며 재시작 후에도 공개 집계 캐시를 재사용합니다."""
    key = canonical_hash(
        [file_sha256(Path(__file__)), path, stores_id, areas_id, stores_hash, areas_hash]
    )
    folder = CACHE_DIR
    target = folder / f"{key}.json"
    with _BUILDING:
        if target.exists():
            try:
                value = json.loads(target.read_text(encoding="utf-8"))
                if value["key"] == key and value["checksum"] == canonical_hash(value["data"]):
                    return value["data"]
            except (OSError, ValueError, KeyError, TypeError):
                # 손상된 공개 집계 캐시는 고정한 원본으로 다시 계산합니다.
                pass
        value = _build_reference(path, stores_id, areas_id)
        folder.mkdir(parents=True, exist_ok=True)
        staging = folder / f"{key}.{uuid4().hex}.tmp"
        staging.write_text(
            canonical_json({"key": key, "data": value, "checksum": canonical_hash(value)}),
            encoding="utf-8",
        )
        staging.replace(target)
        return value


def warm_reference(path=None):
    from app.local_data.adapter import LocalAdapter

    adapter = LocalAdapter(path)
    stores = [v for v in adapter.versions if v["source"] == "stores"]
    areas = [v for v in adapter.versions if v["source"] == "areas"]
    if len(stores) != 1 or len(areas) != 1:
        return False
    city_reference(
        str(adapter.path),
        stores[0]["version_id"],
        areas[0]["version_id"],
        stores[0]["file_hash"],
        areas[0]["file_hash"],
    )
    return True


def attach_reference(adapter, task, data):
    stores = [v for v in adapter.versions if v["source"] == "stores"]
    areas = [v for v in adapter.versions if v["source"] == "areas"]
    quarter = data.get("floating_population", {}).get("period_code")
    if len(stores) != 1 or len(areas) != 1 or stores[0]["quarter"] != quarter:
        data.setdefault("limitations", []).append(
            "같은 분기의 경쟁 참고 자료가 없어 주변 경쟁도 보완을 제한했습니다."
        )
        return
    samples, medical = city_reference(
        str(adapter.path),
        stores[0]["version_id"],
        areas[0]["version_id"],
        stores[0]["file_hash"],
        areas[0]["file_hash"],
    )
    code = data.get("area_selection", {}).get("area_code")
    eligible = [
        row
        for row in samples
        if row["area"] != code
        and haversine_m(task.site.latitude, task.site.longitude, row["latitude"], row["longitude"])
        > 1000
    ]
    # 51개 업종 점수에 공유하며 해당 요청의 고정 버전으로 재구성할 수 있습니다.
    data["score90_reference"] = {
        "quarter": quarter,
        "samples": eligible,
        "store_version_id": stores[0]["version_id"],
        "area_version_id": areas[0]["version_id"],
        "exclude_distance_m": 1000,
    }
    if len(eligible) < 20:
        data.setdefault("limitations", []).append(
            "경쟁 참고 상권이 적어 주변 점포 수의 상대 평가를 적용하지 않았습니다."
        )
    if medical:
        data["score90_medical_subset_distance"] = min(
            haversine_m(task.site.latitude, task.site.longitude, lat, lon) for lat, lon in medical
        )
