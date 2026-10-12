"""주소 하나로 교육환경보호구역을 조회합니다.

    python examples/run_education_zone.py --address "서울특별시 관악구 봉천로 123"
    python examples/run_education_zone.py --address "..." --with-geometry

카카오 주소 검색(GEOCODING_API_KEY)과 V-World(VWORLD_API_KEY) 키가 모두 필요합니다.
좌표가 고시된 구역 폴리곤 안에 드는지를 V-World가 판정하므로 거리는 계산하지 않습니다.
"""

import argparse
import asyncio
import json
import sys

from app.address import GeocodeError, resolve_site
from app.config import load_environment
from app.education_zone import EducationZoneError, find_education_zones


async def run(address: str, *, with_geometry: bool) -> int:
    site = await resolve_site(address)
    print(f"주소: {site.road_address or site.jibun_address}")
    print(f"좌표: {site.latitude}, {site.longitude}\n")

    scan = await find_education_zones(
        site.latitude,
        site.longitude,
        with_geometry=with_geometry,
    )
    print(json.dumps(scan.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if scan.status == "error":
        print("\n조회에 실패했습니다. 보호구역이 없다는 뜻이 아닙니다.", file=sys.stderr)
        return 1
    if not scan.zones:
        print("\n이 좌표는 교육환경보호구역에 들어가지 않습니다.")
        return 0
    print(f"\n보호구역 {len(scan.zones)}건:")
    for zone in scan.zones:
        print(f"  · {zone.name}" + (f" — {zone.note}" if zone.note else ""))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="교육환경보호구역 조회")
    parser.add_argument("--address", required=True, help="도로명 또는 지번 주소")
    parser.add_argument("--with-geometry", action="store_true", help="구역 폴리곤도 받습니다")
    args = parser.parse_args()

    load_environment()
    try:
        return asyncio.run(run(args.address, with_geometry=args.with_geometry))
    except (GeocodeError, EducationZoneError) as exc:
        print(f"실패: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
