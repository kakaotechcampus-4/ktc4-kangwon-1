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

    python examples/build_density_baseline.py                # 이어서 돌기
    python examples/build_density_baseline.py --limit 50     # 맛보기
    python examples/build_density_baseline.py --emit         # 표본으로 경계표만 출력
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.commercial_area.client import SbizApiError, StoreClient  # noqa: E402
from app.agents.commercial_area.config import (  # noqa: E402
    RESTAURANT_MAJOR_NAMES,
    Settings,
    load_dotenv_if_present,
)
from app.agents.commercial_area.trade_areas import load_trade_areas  # noqa: E402

SAMPLE_PATH = Path(__file__).resolve().parent / "commercial_area" / "density_baseline_sample.csv"
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
            count = sum(1 for s in stores if s.major_name in RESTAURANT_MAJOR_NAMES)
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


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="이번에 받을 지점 수")
    parser.add_argument("--emit", action="store_true", help="받아둔 표본으로 경계표만 출력")
    args = parser.parse_args()

    load_dotenv_if_present()
    if args.emit:
        return emit()

    settings = Settings.from_env()
    if not settings.sbiz_service_key:
        print("COMMERCIAL_AREA_API_KEY 가 없습니다.")
        return 1
    asyncio.run(sample(settings, args.limit))
    return emit()


if __name__ == "__main__":
    raise SystemExit(main())
