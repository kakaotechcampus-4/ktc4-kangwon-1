"""지도 분석 도구를 검색어 몇 개로 돌려 봅니다."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.address import GeocodeError, resolve_site
from app.agents.map_analysis import observe
from app.agents.map_analysis.agent import category_code
from app.agents.map_analysis.config import Settings, load_dotenv_if_present
from app.schemas import DEFAULT_RADIUS_M, AnalysisTask, MapLookupPlan, Site


async def run() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", required=True)
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--radius", type=int, default=DEFAULT_RADIUS_M)
    parser.add_argument("--query", action="append", dest="queries")
    parser.add_argument("--industry-code", help="업종 조회 시 서비스 통합 업종 코드")
    args = parser.parse_args()

    load_dotenv_if_present()

    # 좌표를 직접 주면 지오코딩을 건너뛴다. 카카오 요청 한 번을 아끼려는 용도
    if args.lat is None or args.lon is None:
        try:
            site = await resolve_site(args.address)
        except GeocodeError as exc:
            print(f"주소 확인 실패: [{exc.code}] {exc.message}", file=sys.stderr)
            return 1
    else:
        site = Site(
            input_address=args.address,
            road_address=args.address,
            latitude=args.lat,
            longitude=args.lon,
        )

    queries = []
    for query in args.queries or ["지하철역", "초등학교"]:
        code = category_code(query)
        if args.industry_code:
            target = dict(kind="industry", industry_code=args.industry_code, query=query)
        elif code:
            target = dict(kind="infrastructure", facility_code=code)
        else:
            parser.error("업종 키워드는 --industry-code를 함께 지정하세요.")
        queries.append({**target, "why_needed": "주변 현황 확인", "expected_impact": "후보 비교"})
    result = await observe(
        AnalysisTask(request_id="map-example", site=site, radius_m=args.radius),
        MapLookupPlan(action="map_lookup", queries=queries),
        settings=Settings.from_env(),
    )
    print(json.dumps(result.model_dump(exclude_none=True), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
