"""소상공인 API가 허용하는 반경을 확인합니다."""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.agents.commercial_area.client import SbizApiError, StoreClient
from app.agents.commercial_area.config import Settings, load_dotenv_if_present

DEFAULT_LAT = 37.5006
DEFAULT_LON = 127.0364
CANDIDATES = (500, 1000, 1500, 2000, 3000)


async def run() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT)
    parser.add_argument("--lon", type=float, default=DEFAULT_LON)
    parser.add_argument("--radii", type=int, nargs="*", default=list(CANDIDATES))
    args = parser.parse_args()

    load_dotenv_if_present()
    settings = Settings.from_env(max_pages=1)
    if not settings.sbiz_service_key:
        print("SBIZ_SERVICE_KEY가 없습니다. .env에 키를 넣고 다시 실행하세요.")
        return 1

    client = StoreClient(settings)
    print(f"좌표 ({args.lat}, {args.lon}) 기준 반경별 응답 확인")
    print(f"{'반경(m)':>8} {'결과':<10} {'총건수':>10}  비고")
    try:
        for radius in args.radii:
            try:
                _, meta = await client.stores_in_radius(args.lat, args.lon, radius, use_cache=False)
                print(f"{radius:>8} {'성공':<10} {meta['total_count']:>10}  1페이지만 확인")
            except SbizApiError as exc:
                print(f"{radius:>8} {'실패':<10} {'-':>10}  {exc.code} {exc.message[:60]}")
    finally:
        await client.aclose()
    print(f"\n총 API 호출 {client.calls_made}회")
    return 0


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
