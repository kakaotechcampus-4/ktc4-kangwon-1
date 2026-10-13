"""승인된 8개 주소의 v0.2 시험 자료만 수집한다. LLM 생성·호출은 즉시 차단한다."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.address import resolve_site  # noqa: E402
from app.agents.business_lifecycle.agent import analyze as lifecycle  # noqa: E402
from app.agents.business_lifecycle.agent import run_business_lifecycle_agent  # noqa: E402
from app.agents.business_lifecycle.config import Settings as LifecycleSettings  # noqa: E402
from app.agents.business_lifecycle.input_builder import _build_input  # noqa: E402
from app.agents.business_lifecycle.preprocess import (
    preprocess_business_lifecycle_data,  # noqa: E402
)
from app.agents.business_lifecycle.scoring import calculate_lifecycle_scores  # noqa: E402
from app.agents.commercial_area.agent import analyze as commercial  # noqa: E402
from app.agents.commercial_area.client import StoreClient  # noqa: E402
from app.agents.commercial_area.config import Settings as CommercialSettings  # noqa: E402
from app.agents.commercial_area.industries import incomplete_split_codes  # noqa: E402
from app.agents.floating_population.agent import analyze as floating  # noqa: E402
from app.agents.floating_population.client import SeoulOpenDataClient  # noqa: E402
from app.agents.floating_population.config import Settings as FloatingSettings  # noqa: E402
from app.agents.map_analysis.agent import observe  # noqa: E402
from app.config import load_environment  # noqa: E402
from app.education_zone import find_education_zones, scan_site  # noqa: E402
from app.schemas import AnalysisTask, MapLookupPlan, MapQuery  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "backend/cache/rubric_samples"
QUARTER = "20262"
FACILITIES = ("HP8", "SC4", "CT1", "AT4", "PK6", "SW8")
SAMPLES = (
    ("오피스가①", "서울특별시 강남구 테헤란로 152", 100, 180),
    ("오피스가②", "서울특별시 중구 세종대로 110", 80, 160),
    ("대학가", "서울특별시 마포구 와우산로 94", 70, 150),
    ("주거 골목①", "서울특별시 강북구 도봉로89길 13", 50, 120),
    ("주거 골목②", "서울특별시 노원구 동일로186길 3-24", 50, 120),
    ("관광·유흥", "서울특별시 용산구 이태원로 지하 177", 70, 150),
    ("학교 인근", "서울특별시 강남구 선릉로64길 33", 80, 160),
    ("서울 외곽", "서울특별시 은평구 진관2로 15-46", 40, 100),
)


class ForbiddenLLM(BaseException):
    """분석 코드의 일반 예외 수집으로도 숨길 수 없는 LLM 차단."""


def forbid_llm(*args, **kwargs):
    raise ForbiddenLLM("시험 수집에서 LLM 클라이언트 생성은 금지됩니다.")


class FixedQuarterClient(SeoulOpenDataClient):
    async def latest_quarter(self) -> str:
        return QUARTER


class AuditedStores(StoreClient):
    local_meta: dict | None = None
    split_missing: set[str]

    async def stores_in_radius(self, latitude, longitude, radius_m, **kwargs):
        stores, meta = await super().stores_in_radius(latitude, longitude, radius_m, **kwargs)
        if radius_m == 500:
            self.local_meta = meta
            self.split_missing = incomplete_split_codes(stores)
            self.local_complete = not meta.get("truncated") and len(stores) == meta.get("fetched")
        return stores, meta


def reference_quarter(meta: dict) -> str | None:
    raw = str(meta.get("reference_date") or "")
    digits = re.sub(r"\D", "", raw)
    if len(digits) in {6, 8} and 1 <= int(digits[4:6]) <= 12:
        return digits[:4] + str((int(digits[4:6]) - 1) // 3 + 1)
    if len(digits) == 5 and digits[-1] in "1234":
        return digits
    return None


async def run_lifecycle_pipeline(
    area_code, base_quarter, quarter_count, request_id, area_name, settings, detail
):
    async def captured_input(**kwargs):
        raw = await preprocess_business_lifecycle_data(
            area_code, base_quarter, quarter_count, settings=settings
        )
        detail.update(raw.attrs.get("quarterly_detail", {}))
        frame = await asyncio.to_thread(
            calculate_lifecycle_scores, df=raw, quarter_count=quarter_count
        )
        return await asyncio.to_thread(
            _build_input, frame, area_code, base_quarter, quarter_count, request_id, area_name
        )

    with patch("app.agents.business_lifecycle.agent.build_agent_input", new=captured_input):
        return await run_business_lifecycle_agent(
            area_code, base_quarter, quarter_count, request_id, area_name, settings
        )


async def collect(index: int, kind: str, address: str) -> dict:
    site = await resolve_site(address)
    task = AnalysisTask(request_id=f"rubric-{index}", site=site, radius_m=500)
    detail = {}
    settings = LifecycleSettings.from_env(base_quarter_override=QUARTER, quarter_count=12)

    async def pipeline(area_code, base_quarter, quarter_count, request_id, area_name):
        return await run_lifecycle_pipeline(
            area_code, base_quarter, quarter_count, request_id, area_name, settings, detail
        )

    store_settings = CommercialSettings.from_env(ftc_service_key=None)
    stores = AuditedStores(store_settings)
    stores.split_missing = set()
    stores.local_complete = False
    async with FixedQuarterClient(FloatingSettings.from_env()) as population_client:
        try:
            analyses = await asyncio.gather(
                floating(task, settings=FloatingSettings.from_env(), client=population_client),
                lifecycle(task, settings=settings, run_pipeline=pipeline),
                commercial(task, settings=store_settings, store_client=stores),
            )
        finally:
            await stores.aclose()
    plan = MapLookupPlan(
        action="map_lookup",
        queries=[
            MapQuery(
                kind="infrastructure",
                facility_code=f,
                why_needed="C4 승인 시설의 최근접 거리",
                expected_impact="시험 채점 자료 확인",
            )
            for f in FACILITIES
        ],
    )
    zones = await scan_site(site, lambda s: find_education_zones(s.latitude, s.longitude))
    facilities = await observe(task, plan, generate_mapping=forbid_llm)
    result = {
        "address": address,
        "kind": kind,
        "site": site.model_dump(mode="json"),
        "education_zones": zones.model_dump(mode="json"),
        "facilities": facilities.model_dump(mode="json"),
        "lifecycle_quarterly": detail,
        "commercial_collection_complete": stores.local_complete,
        "commercial_split_missing": sorted(stores.split_missing),
        "commercial_reference_quarter": reference_quarter(stores.local_meta or {}),
        "agent_status": {},
        "llm_calls": 0,
    }
    for analysis in analyses:
        result[analysis.agent_id] = analysis.data
        result[analysis.agent_id.split("_")[0] + "_warnings"] = analysis.warnings
        result["agent_status"][analysis.agent_id] = {
            "status": analysis.status,
            "error": analysis.error.model_dump() if analysis.error else None,
        }
    return result


async def run(output: Path) -> None:
    import httpx

    output = await asyncio.to_thread(output.resolve)
    if output.is_relative_to(ROOT) and not output.is_relative_to(ROOT / "backend/cache"):
        raise ValueError("실데이터 출력은 저장소 밖 또는 backend/cache만 허용합니다.")
    await asyncio.to_thread(output.mkdir, parents=True, exist_ok=True)
    original_send = httpx.AsyncClient.send
    prior = {}
    for index in range(1, 9):
        path = output / f"sample-{index:02}.json"
        if await asyncio.to_thread(path.exists):
            prior[index] = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
    reserves = {i: s.get("diagnostic_budget_reserve", 0) for i, s in prior.items()}
    total_reserve = sum(reserves.values())
    total = sum(s.get("http_calls", 0) for s in prior.values())
    calls = Counter()
    current = 0

    async def guarded_send(self, request, *args, **kwargs):
        nonlocal total, current
        if current + reserves.get(index, 0) >= 300 or total + total_reserve >= 2400:
            raise RuntimeError("승인된 HTTP 호출 상한에 도달했습니다.")
        current += 1
        total += 1
        calls[request.url.host] += 1
        return await original_send(self, request, *args, **kwargs)

    with (
        patch("openai.AsyncOpenAI", side_effect=forbid_llm),
        patch("openai.OpenAI", side_effect=forbid_llm),
        patch("app.llm.session._new_client", side_effect=forbid_llm),
        patch.object(httpx.AsyncClient, "send", guarded_send),
    ):
        for index, (kind, address, _, _) in enumerate(SAMPLES, 1):
            path = output / f"sample-{index:02}.json"
            previous = prior.get(index, {})
            if (
                previous
                and not previous.get("collection_error")
                and previous.get("agent_status", {}).get("business_lifecycle", {}).get("status")
                != "error"
            ):
                print(f"[{index}/8] 기존 표본 유지: {address}", flush=True)
                continue
            current = previous.get("http_calls", 0)
            calls.update(previous.get("http_by_host", {}))
            calls.clear()
            try:
                sample = await collect(index, kind, address)
            except Exception as exc:
                sample = {
                    "error_code": getattr(exc, "code", None),
                    "address": address,
                    "kind": kind,
                    "collection_error": type(exc).__name__,
                    "llm_calls": 0,
                }
            sample["http_calls"] = current
            sample["diagnostic_budget_reserve"] = reserves.get(index, 0)
            sample["http_by_host"] = dict(calls)
            await asyncio.to_thread(
                path.write_text,
                json.dumps(sample, ensure_ascii=False, indent=2, allow_nan=False),
                encoding="utf-8",
            )
            print(
                f"[{index}/8] {address} · HTTP {current}회 · LLM 0회 "
                f"· {sample.get('agent_status', sample.get('collection_error'))}",
                flush=True,
            )
    print(f"수집 누적 계측 HTTP {total}회 · 별도 진단 예산 {total_reserve}회 · LLM 0회", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="사용자 승인 후 실제 수집")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not args.run:
        print(json.dumps(SAMPLES, ensure_ascii=False, indent=2))
        return 0
    load_environment()
    asyncio.run(run(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
