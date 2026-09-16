"""API 응답만 목업으로 교체하고 분석·판단 LLM은 실제 호출합니다."""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from datetime import date
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from dotenv import load_dotenv

from app.agents import commercial_area, floating_population
from app.agents.commercial_area.client import StoreClient
from app.agents.commercial_area.config import Settings as CommercialSettings
from app.agents.commercial_area.franchise import _brand_items, save_brands
from app.agents.floating_population.client import SeoulOpenDataClient
from app.agents.floating_population.config import Settings as FloatingSettings
from app.agents.orchestration import build_react_agents, run_react
from app.schemas import Site

EXAMPLES = Path(__file__).resolve().parent
DEFAULT_INPUT = EXAMPLES / "fixtures" / "api_responses.json"


def mock_transport(fixture: dict) -> httpx.MockTransport:
    """등록된 요청만 처리하며 실제 데이터 API로 우회하지 않습니다."""
    responses = fixture["responses"]

    def respond(request: httpx.Request) -> httpx.Response:
        parts = request.url.path.strip("/").split("/")
        if request.method != "GET":
            raise ValueError("목업은 GET만 지원합니다.")
        if request.url.host == "openapi.seoul.go.kr":
            if len(parts) not in (5, 6) or parts[:2] != ["mock-key", "json"]:
                raise ValueError("지원하지 않는 서울시 목업 요청입니다.")
            service, start, end = parts[2], int(parts[3]), int(parts[4])
            if service == "TbgisTrdarRelm" and len(parts) == 5:
                payload = copy.deepcopy(responses["areas"])
            elif service == "VwsmTrdarFlpopQq" and len(parts) == 6:
                payload = copy.deepcopy(
                    responses["population"].get(
                        parts[5],
                        {
                            service: {
                                "list_total_count": 0,
                                "RESULT": {"CODE": "INFO-200"},
                                "row": [],
                            },
                        },
                    )
                )
            else:
                raise ValueError("지원하지 않는 서울시 목업 서비스입니다.")
            payload[service]["row"] = payload[service]["row"][start - 1 : end]
        elif request.url.host == "apis.data.go.kr":
            operation, params = parts[-1], request.url.params
            if request.url.path != f"/B553077/api/open/sdsc2/{operation}":
                raise ValueError("지원하지 않는 상권 목업 경로입니다.")
            if operation == "storeListInRadius" and params.get("radius") in {"500", "2000"}:
                site = fixture["site"]
                if (float(params["cy"]), float(params["cx"])) != (
                    site["latitude"],
                    site["longitude"],
                ):
                    raise ValueError("목업 주소와 조회 좌표가 다릅니다.")
                key = "stores_" + params["radius"]
            elif operation == "storeListInDong" and params.get("key") == "11710":
                key = "stores_district"
            else:
                raise ValueError("지원하지 않는 상권 목업 조회입니다.")
            payload = copy.deepcopy(responses[key])
            page, size = int(params["pageNo"]), int(params["numOfRows"])
            body = payload["response"]["body"]
            body["items"] = body["items"][(page - 1) * size : page * size]
        else:
            raise ValueError("등록되지 않은 목업 데이터 API입니다.")
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(respond)


async def run(fixture: dict):
    """원본 파싱·계산은 실제 코드로 수행하고 모델도 실제 호출합니다."""
    site = Site.model_validate(fixture["site"])

    async def resolve(address: str) -> Site:
        if address != site.input_address:
            raise ValueError("지원하지 않는 목업 주소입니다.")
        return site

    async def with_notice(task, *, analyze):
        result = await analyze(task)
        result.warnings.append("API 목업 기반 가상 분석입니다. 실제 개롱역 관측값이 아닙니다.")
        return result

    # 실제 데이터 캐시와 섞이지 않도록 실행별 임시 폴더를 사용합니다.
    with TemporaryDirectory(prefix="chaeum-api-mock-") as temporary:
        ca_settings = CommercialSettings.from_env(
            cache_dir=Path(temporary),
            sbiz_service_key="mock-key",
            ftc_service_key=None,
            analysis_radius_m=500,
            lq_radius_candidates=(2000,),
            lq_cache_grid_m=0,
            page_size=2,
            max_retries=0,
        )
        fp_settings = FloatingSettings(api_key="mock-key", analysis_radius_m=500, trend_quarters=2)
        # 브랜드 조회는 HTTP 주입이 없어 목업 원본을 파싱해 기존 캐시 경로로 전달합니다.
        brands = [str(row["brandNm"]) for row in _brand_items(fixture["responses"]["brands"])]
        if not brands:
            raise ValueError("브랜드 목업에는 한 개 이상의 브랜드가 필요합니다.")
        save_brands(ca_settings, brands)
        async with httpx.AsyncClient(transport=mock_transport(fixture)) as http:
            async with (
                SeoulOpenDataClient(
                    fp_settings,
                    http=http,
                    today=date.fromisoformat(fixture["today"]),
                ) as population_client,
                StoreClient(ca_settings, client=http) as store_client,
            ):
                agents = build_react_agents()
                agents["floating_population"] = partial(
                    with_notice,
                    analyze=partial(
                        floating_population.analyze,
                        settings=fp_settings,
                        client=population_client,
                    ),
                )
                agents["commercial_area"] = partial(
                    with_notice,
                    analyze=partial(
                        commercial_area.analyze,
                        settings=ca_settings,
                        store_client=store_client,
                    ),
                )
                return await run_react(site.input_address, resolve=resolve, agents=agents)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="API 응답 목업 JSON")
    args = parser.parse_args()
    load_dotenv(EXAMPLES.parent / ".env", override=False)
    print("데이터 API는 목업, LLM은 실제 연결입니다. 모델 호출 비용이 발생합니다.", file=sys.stderr)
    print(
        "좌표·인구·점포는 가상 값이며 실제 개롱역 입지 판단에 사용할 수 없습니다.", file=sys.stderr
    )
    try:
        fixture = json.loads(args.input.read_text(encoding="utf-8"))
        result = asyncio.run(run(fixture))
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(f"실행 실패: {exc}", file=sys.stderr)
        return 1
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
