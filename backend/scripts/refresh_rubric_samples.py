"""v0.3 재조회: 기존 표본의 보호구역 8회·최근접 상권 개폐업 3곳만 갱신한다."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.agents.business_lifecycle.agent import analyze  # noqa: E402
from app.agents.business_lifecycle.area_resolver import (  # noqa: E402
    polygon_contains_point,
    resolve_area,
)
from app.agents.business_lifecycle.config import Settings  # noqa: E402
from app.config import load_environment  # noqa: E402
from app.education_zone import (  # noqa: E402
    EducationZoneSettings,
    find_education_zones,
)
from app.geo import to_epsg5181  # noqa: E402
from app.schemas import AnalysisTask, Site  # noqa: E402
from scripts.collect_rubric_samples import (  # noqa: E402
    OUTPUT,
    QUARTER,
    forbid_llm,
    run_lifecycle_pipeline,
)

KEY_ERRORS = {"INCORRECT_KEY", "INVALID_KEY", "UNAVAILABLE_KEY", "CONFIG_ERROR"}
CHANGED = {3, 7, 8}


def checked_zones(zones: list[dict], latitude: float, longitude: float) -> list[dict]:
    x, y = to_epsg5181(latitude, longitude)
    result = []
    for zone in zones:
        geometry = zone.get("geometry") or {}
        coordinates = geometry.get("coordinates")
        if not coordinates or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            raise ValueError("보호구역 폴리곤을 검증할 수 없습니다.")
        polygons = [coordinates] if geometry["type"] == "Polygon" else coordinates
        # 경계 허용오차는 미터 좌표 기준이므로 경위도를 먼저 투영한다.
        projected = [
            [[to_epsg5181(point[1], point[0]) for point in ring] for ring in rings]
            for rings in polygons
        ]
        if any(polygon_contains_point(rings, x, y) for rings in projected):
            result.append(zone)
    return result


def selection_data(area):
    return {
        "selection_method": area.selection_method,
        "distance_m": area.selection_distance_m,
        "distance_basis": "polygon_edge",
        "area_code": area.area_code,
        "area_name": area.area_name,
    }


async def save(path: Path, data: dict):
    await asyncio.to_thread(
        path.write_text,
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


async def run() -> int:
    paths = sorted(await asyncio.to_thread(lambda: list(OUTPUT.glob("sample-*.json"))))
    if len(paths) != 8:
        raise ValueError("기존 8개 표본이 필요합니다.")
    samples = [json.loads(await asyncio.to_thread(p.read_text, encoding="utf-8")) for p in paths]
    sites = [Site.model_validate(s["site"]) for s in samples]
    settings = Settings.from_env(base_quarter_override=QUARTER, quarter_count=12)
    areas = [await asyncio.to_thread(resolve_area, site, settings) for site in sites]
    for i in CHANGED:
        print(f"개폐업 재선택 {i}: {areas[i - 1].area_name} · {areas[i - 1].selection_distance_m}m")
    print("예상 HTTP 44회=G 8회+개폐업 3곳×12분기. 상한 100회. LLM 0회", flush=True)
    backup = OUTPUT / "before-v03"
    if not await asyncio.to_thread(backup.exists):
        await asyncio.to_thread(backup.mkdir)
        for path in paths + [OUTPUT / "dryrun-results.json", OUTPUT / "dryrun-report.md"]:
            if await asyncio.to_thread(path.exists):
                await asyncio.to_thread(shutil.copy2, path, backup / path.name)
    zone_settings = replace(EducationZoneSettings.from_env(), max_retries=0)
    calls = Counter()
    phase = "G"
    index = 0
    original = httpx.AsyncClient.send

    async def gate(self, request, *args, **kwargs):
        if sum(calls.values()) >= 100:
            raise RuntimeError("HTTP 100회 상한 초과")
        if phase == "G" and calls[phase, index] >= 1:
            raise RuntimeError("G는 주소당 HTTP 1회만 허용")
        calls[phase, index] += 1
        return await original(self, request, *args, **kwargs)

    async def finish():
        await save(
            OUTPUT / "refresh-v03-audit.json",
            {
                "http_calls": sum(calls.values()),
                "calls": {f"{p}-{i}": n for (p, i), n in calls.items()},
                "llm_calls": 0,
            },
        )

    with (
        patch("openai.AsyncOpenAI", side_effect=forbid_llm),
        patch("openai.OpenAI", side_effect=forbid_llm),
        patch("app.llm.session._new_client", side_effect=forbid_llm),
        patch.object(httpx.AsyncClient, "send", gate),
    ):
        for index, (sample, site, area, path) in enumerate(
            zip(samples, sites, areas, paths, strict=True), 1
        ):
            try:
                scan = await find_education_zones(
                    site.latitude, site.longitude, with_geometry=True, settings=zone_settings
                )
                zones = scan.model_dump(mode="json")
                if zones["status"] == "ok":
                    zones["zones"] = checked_zones(zones["zones"], site.latitude, site.longitude)
                    zones["contains_verified"] = True
            except Exception as exc:
                zones = {
                    "status": "error",
                    "zones": [],
                    "error": {"code": getattr(exc, "code", "GEOMETRY_UNVERIFIED")},
                }
            sample["education_zones"] = zones
            if sample.get("business_lifecycle"):
                sample["business_lifecycle"]["metadata"]["area_resolver"].update(
                    selection_data(area)
                )
            await save(path, sample)
            code = (zones.get("error") or {}).get("code")
            print(
                f"G {index}: {zones['status']} · HTTP {calls['G', index]}회 · 오류 코드 {code}",
                flush=True,
            )
            if code in KEY_ERRORS:
                await finish()
                print("보호구역 키 오류로 즉시 중단했습니다. 키·Referer 값은 출력하지 않습니다.")
                return 2
        phase = "S"
        for index in sorted(CHANGED):
            sample, site, area, path = (
                samples[index - 1],
                sites[index - 1],
                areas[index - 1],
                paths[index - 1],
            )
            detail = {}

            async def pipeline(
                area_code, base_quarter, quarter_count, request_id, area_name, snapshot=detail
            ):
                return await run_lifecycle_pipeline(
                    area_code,
                    base_quarter,
                    quarter_count,
                    request_id,
                    area_name,
                    settings,
                    snapshot,
                )

            result = await analyze(
                AnalysisTask(request_id=f"rubric-v03-{index}", site=site, radius_m=500),
                settings=settings,
                area_resolver=lambda s, c, selected=area: selected,
                run_pipeline=pipeline,
            )
            sample["business_lifecycle"] = result.data
            sample["business_warnings"] = result.warnings
            sample["lifecycle_quarterly"] = detail
            sample["agent_status"]["business_lifecycle"] = {
                "status": result.status,
                "error": result.error.model_dump() if result.error else None,
            }
            if result.data:
                result.data["metadata"]["area_resolver"].update(selection_data(area))
            sample["http_calls_v03"] = calls["G", index] + calls["S", index]
            await save(path, sample)
            print(
                f"S {index}: {result.status} · HTTP {calls['S', index]}회 · {area.area_name}",
                flush=True,
            )
    await finish()
    print(f"재조회 HTTP {sum(calls.values())}회 · LLM 0회")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        print("예상 HTTP 44회. --run은 승인된 재조회만 실행합니다.")
        return 0
    sys.stdout.reconfigure(encoding="utf-8")
    load_environment()
    try:
        return asyncio.run(run())
    except Exception as exc:
        print(f"재조회 중단: {type(exc).__name__}. 키·응답 원문은 출력하지 않습니다.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
