"""서울시 상권 영역 1,650곳을 CSV로 받는다. 분기마다 한 번 돌리면 된다.

받는 것은 서울 열린데이터광장 `TbgisTrdarRelm`(상권분석서비스 영역-상권) 하나다.
서울시 상권 API 여러 종 중 **상권 유형과 면적과 좌표가 같은 행에 오는 건 여기뿐**이다.

결과를 패키지에 동봉하므로 런타임에는 서울시 API를 부르지 않는다 — 새 API 키 의존도,
새 실패 모드도 생기지 않는다. 1,650행은 분기마다 바뀌는 정적 자료다.

좌표는 EPSG:5181 미터다. 우리 좌표(WGS84)를 같은 계로 옮겨 비교한다(`trade_areas.py`).

    SEOUL_OPEN_API_KEY=<키> python examples/fetch_seoul_trade_areas.py

키는 https://data.seoul.go.kr 에서 무료로 즉시 발급된다.
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
    PACKAGE_DIR,
    load_dotenv_if_present,
)

OUT_PATH = PACKAGE_DIR / "data" / "seoul_trade_areas.csv"

BASE_URL = "http://openapi.seoul.go.kr:8088"
SERVICE = "TbgisTrdarRelm"
PAGE_SIZE = 1000
MAX_PAGES = 20

COLUMNS = ["code", "name", "kind", "signgu", "adstrd", "x", "y", "area_m2"]


async def fetch_all(key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=60) as client:
        for page in range(MAX_PAGES):
            start = page * PAGE_SIZE + 1
            end = start + PAGE_SIZE - 1
            response = await client.get(f"{BASE_URL}/{key}/json/{SERVICE}/{start}/{end}/")
            response.raise_for_status()
            try:
                payload = response.json()
            except json.JSONDecodeError:
                raise SystemExit(response.text[:300]) from None
            body = payload.get(SERVICE)
            if body is None:
                raise SystemExit(json.dumps(payload, ensure_ascii=False)[:300])
            result = body.get("RESULT") or {}
            if result.get("CODE") not in (None, "INFO-000"):
                raise SystemExit(f"{result.get('CODE')} {result.get('MESSAGE')}")
            page_rows = body.get("row") or []
            if not page_rows:
                break
            rows.extend(page_rows)
            if len(page_rows) < PAGE_SIZE:
                break
    return rows


def to_record(row: dict[str, Any]) -> dict[str, Any] | None:
    try:
        x = float(row["XCNTS_VALUE"])
        y = float(row["YDNTS_VALUE"])
        area = float(row.get("RELM_AR") or 0.0)
    except (KeyError, TypeError, ValueError):
        return None
    code = str(row.get("TRDAR_CD") or "").strip()
    if not code or area <= 0:
        return None
    return {
        "code": code,
        "name": str(row.get("TRDAR_CD_NM") or "").strip(),
        "kind": str(row.get("TRDAR_SE_CD_NM") or "").strip(),
        "signgu": str(row.get("SIGNGU_CD_NM") or "").strip(),
        "adstrd": str(row.get("ADSTRD_CD_NM") or "").strip(),
        "x": round(x, 2),
        "y": round(y, 2),
        "area_m2": round(area, 1),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="이미 있는 CSV를 덮어씁니다")
    args = parser.parse_args()

    if OUT_PATH.exists() and not args.force:
        print(f"{OUT_PATH.name} 이 이미 있습니다. 덮어쓰려면 --force")
        return 0

    load_dotenv_if_present()
    key = os.environ.get("SEOUL_OPEN_API_KEY")
    if not key:
        print("SEOUL_OPEN_API_KEY 가 없습니다. https://data.seoul.go.kr 에서 발급받으세요.")
        return 1

    raw = asyncio.run(fetch_all(key))
    records = [r for r in (to_record(row) for row in raw) if r]
    dropped = len(raw) - len(records)
    records.sort(key=lambda r: r["code"])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(records)

    kinds: dict[str, int] = {}
    for record in records:
        kinds[record["kind"]] = kinds.get(record["kind"], 0) + 1
    print(f"상권 {len(records):,}곳 → {OUT_PATH.name}")
    print(f"  유형 {kinds}")
    if dropped:
        print(f"  ⚠️ 좌표나 면적이 없어 버린 행 {dropped}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
