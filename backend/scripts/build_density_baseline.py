"""서울 상권 1,650곳을 표본으로 음식점 밀도 분포를 만든다. 결과는 백분위 경계표 상수다.

## 왜 상권 면적을 안 쓰는가

서울시 상권 폴리곤 면적은 중앙값이 약 0.07km² 인데 우리 분모는 반경 500m 원 0.7854km² 다.
10배 넘게 차이 나서, 상권 면적 기준 분포에 우리 값을 대면 **어디를 찍든 최하위**로 나온다.
`INDEX` §8 이 논문 임계값을 못 쓴다고 한 이유가 백분위에서 그대로 재현되는 것이다.

그래서 **상권 중심좌표에 우리와 똑같이 반경 500m 원을 씌워 음식점을 센다.** 사과 대 사과가 되고
`restaurant_density.value` 의 의미가 바뀌지 않는다.

## 비용

소상공인 API 를 1,650지점 부른다(일 쿼터 10,000). 기존 `StoreClient` 의 캐시·재시도·동시성
제한을 그대로 쓴다. **중간에 끊겨도 이어서 돌 수 있게** 지점별 결과를 그때그때 파일에 남긴다.

    python scripts/build_density_baseline.py                # 이어서 돌기
    python scripts/build_density_baseline.py --limit 50     # 맛보기
    python scripts/build_density_baseline.py --emit         # 기존 음식점 표본으로 출력
    python scripts/build_density_baseline.py --industries --seoul-csv D:/s.csv --quarter 20262
    python scripts/build_density_baseline.py --industries --emit  # 외부 호출 없음
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from pprint import pformat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.commercial_area.client import SbizApiError, StoreClient, to_store  # noqa: E402
from app.agents.commercial_area.config import (  # noqa: E402
    RESTAURANT_MAJOR_NAMES,
    Settings,
    load_dotenv_if_present,
)
from app.agents.commercial_area.industries import incomplete_split_codes, map_stores  # noqa: E402
from app.agents.commercial_area.metrics import haversine_m  # noqa: E402
from app.agents.commercial_area.trade_areas import SeoulTradeArea, load_trade_areas  # noqa: E402
from app.industries.catalog import CATALOG_VERSION, INDUSTRIES  # noqa: E402

SAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "commercial_area"
    / "density_baseline_sample.csv"
)
COLUMNS = ["code", "name", "kind", "restaurant_count", "density"]

# 유동인구 baseline.py 의 SCALE_PERCENTILES 와 같은 5%p 간격.
STEPS = tuple(range(5, 100, 5))


def area_km2(radius_m: int) -> float:
    return math.pi * radius_m**2 / 1_000_000


def load_done() -> dict[str, dict[str, str]]:
    if not SAMPLE_PATH.exists():
        return {}
    with SAMPLE_PATH.open(encoding="utf-8-sig", newline="") as handle:
        return {row["code"]: row for row in csv.DictReader(handle) if row.get("code")}


def append(row: dict) -> None:
    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    new = not SAMPLE_PATH.exists()
    with SAMPLE_PATH.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if new:
            writer.writeheader()
        writer.writerow(row)


def percentile_table(values: list[float]) -> list[float]:
    """오름차순 분포에서 5%p 간격 경계값. 유동인구와 같은 방식."""
    ordered = sorted(values)
    last = len(ordered) - 1
    bounds = []
    for step in STEPS:
        position = step / 100 * last
        low = math.floor(position)
        high = min(low + 1, last)
        weight = position - low
        bounds.append(round(ordered[low] + (ordered[high] - ordered[low]) * weight, 2))
    return bounds


async def sample(settings: Settings, limit: int | None) -> None:
    areas = load_trade_areas()
    if not areas:
        raise SystemExit(
            "seoul_trade_areas.csv 가 없습니다. fetch_seoul_trade_areas.py 를 먼저 돌리세요."
        )

    done = load_done()
    todo = [a for a in areas if a.code not in done]
    if limit:
        todo = todo[:limit]
    print(f"상권 {len(areas):,}곳 · 이미 받은 것 {len(done):,} · 이번에 {len(todo):,}")
    if not todo:
        return

    client = StoreClient(settings)
    radius = settings.analysis_radius_m
    failures = 0
    try:
        for index, area in enumerate(todo, 1):
            lat, lon = _to_wgs84(area.x, area.y)
            try:
                stores, _meta = await client.stores_in_radius(lat, lon, radius)
            except SbizApiError as exc:
                failures += 1
                print(f"  [{index}/{len(todo)}] {area.name} 실패 — {exc.message}")
                continue
            count = sum(1 for s in map_stores(stores) if s.major_name in RESTAURANT_MAJOR_NAMES)
            append(
                {
                    "code": area.code,
                    "name": area.name,
                    "kind": area.kind,
                    "restaurant_count": count,
                    "density": round(count / area_km2(radius), 4),
                }
            )
            if index % 25 == 0 or index == len(todo):
                print(f"  [{index}/{len(todo)}] {area.name} 음식점 {count}개")
    finally:
        await client.aclose()
    if failures:
        print(f"  ⚠️ 실패 {failures}건 — 다시 돌리면 이어서 받습니다")


def _to_wgs84(x: float, y: float) -> tuple[float, float]:
    """EPSG:5181 → WGS84. 정변환을 뉴턴식으로 되돌린다(역투영식을 따로 두지 않으려고).

    상권 중심점 하나당 몇 번 반복이면 1cm 아래로 수렴한다.
    """
    from app.geo import to_epsg5181

    lat, lon = 37.5, 127.0
    for _ in range(12):
        gx, gy = to_epsg5181(lat, lon)
        dx, dy = x - gx, y - gy
        if abs(dx) < 0.01 and abs(dy) < 0.01:
            break
        lat += dy / 111_320
        lon += dx / (111_320 * math.cos(math.radians(lat)))
    return lat, lon


def emit() -> int:
    done = load_done()
    if not done:
        print("표본이 없습니다.")
        return 1
    values = [float(row["density"]) for row in done.values()]
    bounds = percentile_table(values)
    ordered = sorted(values)
    median = ordered[len(ordered) // 2]
    print(f"표본 {len(values):,}곳")
    print(f"  최소 {ordered[0]:,.1f} · 중앙 {median:,.1f} · 최대 {ordered[-1]:,.1f}")
    print()
    print("SEOUL_RESTAURANT_DENSITY_PERCENTILES = (")
    for step, value in zip(STEPS, bounds, strict=True):
        print(f"    {value},  # {step}%")
    print(")")
    kinds: dict[str, list[float]] = {}
    for row in done.values():
        kinds.setdefault(row["kind"], []).append(float(row["density"]))
    print()
    print("유형별 중앙값:")
    for kind, vals in sorted(kinds.items(), key=lambda kv: -len(kv[1])):
        s = sorted(vals)
        print(f"  {kind:<8} {len(s):>5}곳  중앙 {s[len(s) // 2]:,.1f}")
    return 0


INDUSTRY_SAMPLE_PATH = Path(__file__).resolve().parents[1] / "cache/industry_density_sample.csv"
INDUSTRY_COLUMNS = [
    "code",
    "name",
    "radius_m",
    "catalog_version",
    "reference_date",
    "raw_store_count",
    "unmapped_count",
    "blocked_codes",
    "counts",
]


def industry_counts(stores) -> tuple[dict[str, int], set[str]]:
    """같은 반경의 원문을 한 번 매핑해 51업종을 함께 집계합니다."""
    mapped = map_stores(stores)
    counts = Counter(s.middle_code for s in mapped)
    return {code: counts.get(code, 0) for code in INDUSTRIES}, incomplete_split_codes(stores)


def load_industry_done() -> dict[str, dict[str, str]]:
    if not INDUSTRY_SAMPLE_PATH.exists():
        return {}
    with INDUSTRY_SAMPLE_PATH.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = {}
    for row in rows:
        if row["catalog_version"] != CATALOG_VERSION or row["radius_m"] != "500":
            continue
        counts = json.loads(row["counts"])
        blocked = json.loads(row["blocked_codes"])
        if (
            set(counts) != set(INDUSTRIES)
            or any(type(v) is not int or v < 0 for v in counts.values())
            or not set(blocked) <= set(INDUSTRIES)
        ):
            raise ValueError("업종별 밀도 표본의 형식이 잘못되었습니다.")
        result[row["code"]] = row
    return result


from app.agents.commercial_area.client import CSV_FIELDS  # noqa: E402


def sample_csv(path: Path, quarter: str, areas: tuple[SeoulTradeArea, ...]) -> list[dict]:
    """서울 파일을 격자에 넣고 기존 중심·반경의 점포를 찾는다. HTTP 호출은 없다."""
    if path.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        raise ValueError("원문 CSV는 저장소 밖에 두세요.")
    if len(quarter) != 5 or not quarter.isdigit() or quarter[-1] not in "1234":
        raise ValueError("파일 기준 분기는 YYYYQ(예: 20262) 형식이어야 합니다.")
    if not areas:
        raise ValueError("상권 중심점 파일이 없습니다.")
    grid = defaultdict(list)
    seen = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            CSV_FIELDS[k]
            for k in ("bizesId", "indsLclsCd", "indsMclsCd", "indsSclsCd", "lat", "lon")
        } | {"시도명"}
        if not required <= set(reader.fieldnames or []):
            raise ValueError(f"필수 열 누락: {sorted(required - set(reader.fieldnames or []))}")
        for number, row in enumerate(reader, 2):
            if row["시도명"] != "서울특별시":
                raise ValueError(f"{number}행: 서울 CSV만 사용할 수 있습니다.")
            store = to_store({key: row.get(column) for key, column in CSV_FIELDS.items()})
            if (
                store is None
                or not store.store_id
                or store.latitude is None
                or store.longitude is None
                or not math.isfinite(store.latitude)
                or not math.isfinite(store.longitude)
                or not 37 <= store.latitude <= 38
                or not 126 <= store.longitude <= 128
            ):
                raise ValueError(f"{number}행: 점포 ID·분류·좌표가 잘못되었습니다.")
            if store.store_id in seen:
                raise ValueError(f"{number}행: 중복 점포 ID입니다.")
            seen.add(store.store_id)
            grid[math.floor(store.latitude * 100), math.floor(store.longitude * 100)].append(store)
    if not seen:
        raise ValueError("점포가 없는 파일입니다.")
    result = []
    for area in areas:
        lat, lon = _to_wgs84(area.x, area.y)
        # 서울에서 500m는 0.01도보다 작다. 인접 격자까지 후보를 모은 뒤 실제 거리로 거른다.
        gx, gy = math.floor(lat * 100), math.floor(lon * 100)
        stores = [
            store
            for x in range(gx - 1, gx + 2)
            for y in range(gy - 1, gy + 2)
            for store in grid.get((x, y), [])
            if haversine_m(lat, lon, store.latitude, store.longitude) <= 500
        ]
        counts, blocked = industry_counts(stores)
        result.append(
            {
                "code": area.code,
                "name": area.name,
                "radius_m": 500,
                "catalog_version": CATALOG_VERSION,
                "reference_date": quarter,
                "raw_store_count": len(stores),
                "unmapped_count": len(stores) - sum(counts.values()),
                "blocked_codes": json.dumps(sorted(blocked)),
                "counts": json.dumps(counts, ensure_ascii=False),
            }
        )
    print(f"파일 점포 {len(seen):,}개 · 상권 {len(result):,}곳 · 기준 {quarter} · HTTP 0회")
    return result


def write_industry_sample(rows: list[dict]) -> None:
    INDUSTRY_SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INDUSTRY_SAMPLE_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDUSTRY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def emit_industries() -> int:
    done = load_industry_done()
    expected = {area.code for area in load_trade_areas()}
    done = {code: row for code, row in done.items() if code in expected}
    if not done:
        print("51업종 밀도 표본이 없습니다.")
        return 1
    quarters = {row["reference_date"] for row in done.values()}
    if len(quarters) != 1 or not next(iter(quarters)):
        raise ValueError("파일 기준 분기가 없거나 섞인 표본입니다.")
    print(
        f"# 원천: 소상공인시장진흥공단_상가(상권)정보 서울 CSV · 기준 분기 {next(iter(quarters))}"
    )
    print("# 반경 500m · 단위 개/km² · 업종 체계 " + CATALOG_VERSION)
    percentiles = {}
    sample_counts = {}
    for code in INDUSTRIES:
        values = [
            json.loads(row["counts"])[code] / area_km2(500)
            for row in done.values()
            if code not in json.loads(row["blocked_codes"])
        ]
        sample_counts[code] = len(values)
        if values:
            percentiles[code] = dict(zip(STEPS, percentile_table(values), strict=True))
    complete = set(done) == expected and all(n == len(expected) for n in sample_counts.values())
    print(f"표본 {len(done)}/{len(expected)}곳 · 완전 기준선={complete}")
    print("INDUSTRY_SAMPLE_COUNTS = " + pformat(sample_counts))
    print("SEOUL_INDUSTRY_DENSITY_PERCENTILES = " + pformat(percentiles))
    medians = {code: values[50] for code, values in percentiles.items()}
    print("SEOUL_INDUSTRY_MEDIAN_DENSITY = " + pformat(medians))
    print("분할 기준선 부족·부분 수집은 승인 전 운영 기준선으로 사용하지 않습니다.")
    return 0 if complete else 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="이번에 받을 지점 수")
    parser.add_argument("--emit", action="store_true", help="받아둔 표본으로 경계표만 출력")
    parser.add_argument("--industries", action="store_true", help="51업종별 반경 500m 분포 측정")
    parser.add_argument("--seoul-csv", type=Path, help="저장소 밖 서울 상가 UTF-8 CSV 경로")
    parser.add_argument("--quarter", help="파일 기준 분기 YYYYQ, 예: 20262")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("표본 수는 양수여야 합니다.")
    if (args.seoul_csv or args.quarter) and not args.industries:
        parser.error("CSV 옵션은 --industries와 함께 사용하세요.")

    if args.emit:
        return emit_industries() if args.industries else emit()

    if args.industries:
        if not args.seoul_csv or not args.quarter or args.limit is not None:
            parser.error("51업종은 --seoul-csv와 --quarter가 필요하며 --limit은 쓰지 않습니다.")
        areas = load_trade_areas()
        if len(areas) != 1650:
            parser.error("기존 1,650개 상권 중심점이 필요합니다.")
        write_industry_sample(sample_csv(args.seoul_csv, args.quarter, areas))
        return emit_industries()

    load_dotenv_if_present()
    settings = Settings.from_env()
    if not settings.sbiz_service_key:
        print("COMMERCIAL_AREA_API_KEY 가 없습니다.")
        return 1
    asyncio.run(sample(settings, args.limit))
    return emit()


if __name__ == "__main__":
    raise SystemExit(main())
