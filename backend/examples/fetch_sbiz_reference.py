"""소상공인 상가정보 API의 참조용 목록 두 종을 CSV로 받는다.

지금 분석 경로에서 쓰지 않는 오퍼레이션이라 검토용으로 따로 뒀다.

    middleUpjongList    업종 중분류 코드 공식 목록
                        지금 마스터는 storeListInRadius 표본에서 긁어 만든다
                        (build_upjong_master.py). 표본에 안 잡힌 업종이 빠질 수 있어
                        공식 목록과 대조가 필요하다.

    storeZoneInRadius   반경 안 상권 목록. trarArea(상권 면적 m²)가 들어 있다.
                        논문 임계값을 못 쓰는 이유 중 "분모가 다르다"(논문은 상권 폴리곤
                        면적, 우리는 반경 원)를 이 값으로 확인할 수 있다.

사용:
    python examples/fetch_sbiz_reference.py
    python examples/fetch_sbiz_reference.py --lat 37.5006 --lon 127.0364 --radius 2000
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.commercial_area.config import (  # noqa: E402
    SBIZ_BASE_URL,
    Settings,
    load_dotenv_if_present,
)

OUT_DIR = Path(__file__).resolve().parent / "commercial_area"

UPJONG_COLUMNS = ["indsLclsCd", "indsLclsNm", "indsMclsCd", "indsMclsNm", "stdrDt"]

# coords(POLYGON WKT)는 한 칸이 6만 자를 넘어 엑셀 셀 한도(32,767자)를 초과한다.
# CSV에는 싣지 않고 원본 JSON으로 따로 남긴다.
ZONE_COLUMNS = [
    "trarNo",
    "mainTrarNm",
    "ctprvnCd",
    "ctprvnNm",
    "signguCd",
    "signguNm",
    "trarArea",
    "coordNum",
    "stdrDt",
]


async def fetch_all(
    settings: Settings, operation: str, query: dict[str, Any], page_size: int = 1000
) -> list[dict[str, Any]]:
    """items 가 빌 때까지 페이지를 넘긴다. 이 두 오퍼레이션은 totalCount 를 주지 않는다."""
    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
        for page in range(1, 51):
            response = await client.get(
                f"{SBIZ_BASE_URL}/{operation}",
                params={
                    "serviceKey": settings.sbiz_service_key,
                    "type": "json",
                    "numOfRows": page_size,
                    "pageNo": page,
                    **query,
                },
            )
            response.raise_for_status()
            payload = response.json()
            header = payload.get("header") or {}
            if header.get("resultCode") not in (None, "00"):
                raise RuntimeError(f"{operation}: {header.get('resultMsg')}")
            items = (payload.get("body") or {}).get("items") or []
            if not items:
                break
            rows.extend(items)
            if len(items) < page_size:
                break
    return rows


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig: 엑셀이 BOM 없이는 한글을 깨뜨린다.
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


async def main_async(args: argparse.Namespace) -> int:
    load_dotenv_if_present()
    settings = Settings.from_env()
    if not settings.sbiz_service_key:
        print("COMMERCIAL_AREA_API_KEY가 없습니다.")
        return 1

    upjong = await fetch_all(settings, "middleUpjongList", {})
    write_csv(OUT_DIR / "upjong_middle_official.csv", UPJONG_COLUMNS, upjong)
    stdr = {row.get("stdrDt") for row in upjong}
    print(f"업종 중분류 {len(upjong)}종 → upjong_middle_official.csv  (기준일 {sorted(stdr)})")

    zones = await fetch_all(
        settings,
        "storeZoneInRadius",
        {"radius": args.radius, "cx": args.lon, "cy": args.lat},
    )
    write_csv(OUT_DIR / "store_zones_in_radius.csv", ZONE_COLUMNS, zones)
    (OUT_DIR / "store_zones_in_radius_raw.json").write_text(
        json.dumps(zones, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    areas = sorted(int(z["trarArea"]) for z in zones if z.get("trarArea"))
    print(f"상권 {len(zones)}곳 → store_zones_in_radius.csv (+ 폴리곤은 _raw.json)")
    if areas:
        mid = areas[len(areas) // 2]
        print(f"  상권 면적 m²: 최소 {areas[0]:,} · 중앙 {mid:,} · 최대 {areas[-1]:,}")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, default=37.508816)
    parser.add_argument("--lon", type=float, default=127.063201)
    parser.add_argument("--radius", type=int, default=2000)
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
