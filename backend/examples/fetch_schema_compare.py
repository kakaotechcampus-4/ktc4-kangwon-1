"""스키마 비교용 원본 덤프 — 소상공인 상가정보 vs 서울시 상권분석서비스(점포-상권).

두 자료의 **필드 구조를 사람이 직접 대조**하라고 만든 것이다. 가공하지 않고 응답 그대로 쓴다.

    소상공인 상가(상권)정보  storeListInRadius   점포 1건 = 1행 (개별 점포)
    서울시 상권분석서비스    VwsmTrdarStorQq     상권×업종×분기 = 1행 (집계)

단위가 다르다는 게 비교의 핵심이다. 우리는 점포 원본, 서울시는 이미 집계된 통계다.

서울시 자료는 열린데이터광장 인증키가 필요하다(무료, 즉시 발급).
키가 없으면 `sample` 키로 5건만 받아 필드 이름만 확인한다.

    https://data.seoul.go.kr  →  로그인  →  인증키 신청

사용:
    python examples/fetch_schema_compare.py
    SEOUL_OPEN_API_KEY=<키> python examples/fetch_schema_compare.py --seoul-max-rows 50000
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.commercial_area.config import (  # noqa: E402
    SBIZ_BASE_URL,
    SBIZ_RADIUS_OPERATION,
    Settings,
    load_dotenv_if_present,
)

OUT_DIR = Path(__file__).resolve().parent / "schema_compare"

SEOUL_BASE = "http://openapi.seoul.go.kr:8088"
SEOUL_SERVICE = "VwsmTrdarStorQq"
SEOUL_PAGE_SIZE = 1000
SAMPLE_PAGE_SIZE = 5


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    if columns is None:
        columns = []
        for row in rows:
            for key in row:
                if key not in columns:
                    columns.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig: 엑셀이 BOM 없이는 한글을 깨뜨린다.
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_field_spec(path: Path, rows: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    """필드별 채움률과 예시값. 이게 스키마 비교의 실제 재료다."""
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)

    spec = []
    for name in columns:
        values = [r.get(name) for r in rows]
        filled = [v for v in values if v not in (None, "", [])]
        sample = next((v for v in filled), "")
        spec.append(
            {
                "source": source,
                "field": name,
                "type": type(sample).__name__ if filled else "unknown",
                "filled": len(filled),
                "total": len(values),
                "fill_rate": round(len(filled) / len(values), 4) if values else 0.0,
                "distinct": len({str(v) for v in filled}),
                "example": str(sample)[:120],
            }
        )
    write_csv(path, spec)
    return spec


async def fetch_sbiz(settings: Settings, lat: float, lon: float, radius: int) -> list[dict]:
    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
        for page in range(1, 101):
            response = await client.get(
                f"{SBIZ_BASE_URL}/{SBIZ_RADIUS_OPERATION}",
                params={
                    "serviceKey": settings.sbiz_service_key,
                    "type": "json",
                    "numOfRows": 1000,
                    "pageNo": page,
                    "radius": radius,
                    "cx": lon,
                    "cy": lat,
                },
            )
            response.raise_for_status()
            payload = response.json()
            header = payload.get("header") or {}
            if header.get("resultCode") not in (None, "00"):
                raise RuntimeError(f"소상공인 API: {header.get('resultMsg')}")
            items = (payload.get("body") or {}).get("items") or []
            if not items:
                break
            rows.extend(items)
            if len(items) < 1000:
                break
    return rows


async def fetch_seoul(key: str, max_rows: int, quarter: str | None) -> tuple[list[dict], int, str]:
    """열린데이터광장은 한 번에 1,000행(sample 키는 5행)까지만 준다."""
    page_size = SAMPLE_PAGE_SIZE if key == "sample" else SEOUL_PAGE_SIZE
    rows: list[dict[str, Any]] = []
    total = 0
    async with httpx.AsyncClient(timeout=60) as client:
        start = 1
        while start <= max_rows:
            end = min(start + page_size - 1, max_rows)
            url = f"{SEOUL_BASE}/{key}/json/{SEOUL_SERVICE}/{start}/{end}/"
            if quarter:
                url += f"{quarter}/"
            response = await client.get(url)
            response.raise_for_status()
            try:
                payload = response.json()
            except json.JSONDecodeError:
                raise RuntimeError(response.text[:300]) from None
            body = payload.get(SEOUL_SERVICE)
            if body is None:
                raise RuntimeError(json.dumps(payload, ensure_ascii=False)[:300])
            result = body.get("RESULT") or {}
            if result.get("CODE") not in (None, "INFO-000"):
                raise RuntimeError(f"{result.get('CODE')} {result.get('MESSAGE')}")
            total = int(body.get("list_total_count") or 0)
            page = body.get("row") or []
            if not page:
                break
            rows.extend(page)
            if len(page) < page_size:
                break
            start = end + 1
    quarters = sorted({str(r.get("STDR_YYQU_CD")) for r in rows})
    return rows, total, quarters[-1] if quarters else ""


async def main_async(args: argparse.Namespace) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv_if_present()
    settings = Settings.from_env()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("── 소상공인 상가(상권)정보 / storeListInRadius ──")
    if not settings.sbiz_service_key:
        print("  COMMERCIAL_AREA_API_KEY가 없습니다.")
        return 1
    sbiz = await fetch_sbiz(settings, args.lat, args.lon, args.radius)
    write_csv(OUT_DIR / "sbiz_stores_raw.csv", sbiz)
    spec = write_field_spec(OUT_DIR / "sbiz_fields.csv", sbiz, "소상공인 상가정보")
    print(f"  점포 {len(sbiz):,}행 · 필드 {len(spec)}개 → sbiz_stores_raw.csv / sbiz_fields.csv")
    empty = [s["field"] for s in spec if s["fill_rate"] == 0.0]
    print(f"  항상 비어 있는 필드 {len(empty)}개: {empty}")

    print()
    print("── 서울시 상권분석서비스(점포-상권) / VwsmTrdarStorQq ──")
    key = os.environ.get("SEOUL_OPEN_API_KEY") or "sample"
    if key == "sample":
        print("  ⚠️ SEOUL_OPEN_API_KEY가 없어 sample 키로 5행만 받습니다(필드 이름 확인용).")
    seoul, total, latest = await fetch_seoul(key, args.seoul_max_rows, args.quarter)
    write_csv(OUT_DIR / "seoul_trdar_stor.csv", seoul)
    sspec = write_field_spec(OUT_DIR / "seoul_fields.csv", seoul, "서울시 상권분석서비스")
    print(f"  {len(seoul):,}행 (전체 {total:,}행) · 필드 {len(sspec)}개 · 최신 분기 {latest}")

    industries = {
        r["SVC_INDUTY_CD"]: r.get("SVC_INDUTY_CD_NM") for r in seoul if r.get("SVC_INDUTY_CD")
    }
    if industries:
        write_csv(
            OUT_DIR / "seoul_industries.csv",
            [{"SVC_INDUTY_CD": c, "SVC_INDUTY_CD_NM": n} for c, n in sorted(industries.items())],
        )
        print(f"  생활밀접업종 {len(industries)}종 → seoul_industries.csv")

    print()
    print(f"모두 {OUT_DIR} 에 있습니다.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, default=37.508816)
    parser.add_argument("--lon", type=float, default=127.063201)
    parser.add_argument("--radius", type=int, default=500)
    parser.add_argument("--seoul-max-rows", type=int, default=5)
    parser.add_argument("--quarter", default=None, help="예: 20262 (비우면 전체 분기)")
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
