"""상권 경쟁 분석 에이전트를 실행합니다."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from app.agents.commercial_area import analyze
from app.agents.commercial_area.config import Settings, load_dotenv_if_present
from app.agents.commercial_area.geocode import GeocodeError, geocode
from app.schemas import AnalysisTask, Site


async def run() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", default="서울특별시 강남구 테헤란로 123")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--radius", type=int)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    load_dotenv_if_present()
    overrides = {"analysis_radius_m": args.radius} if args.radius else {}
    settings = Settings.from_env(**overrides)

    site_kwargs = {}
    if args.lat is None or args.lon is None:
        try:
            found = await geocode(args.address, settings)
        except GeocodeError as exc:
            print(f"주소를 좌표로 바꾸지 못했습니다: {exc}")
            return 1
        lat, lon = found.latitude, found.longitude
        site_kwargs = {
            "road_address": found.road_address,
            "jibun_address": found.jibun_address,
            "detail_address": found.detail_address,
        }
        print(f"지오코딩  {found.provider} · 신뢰도 {found.confidence} → {lat}, {lon}")
        if found.matched_query != args.address.strip():
            print(f"          조회에 쓴 주소: {found.matched_query}")
        if found.detail_address:
            print(f"          분리한 상세주소: {found.detail_address}")
        if found.road_address:
            print(f"          {found.road_address}")
    else:
        lat, lon = args.lat, args.lon

    task = AnalysisTask(
        request_id=str(uuid.uuid4()),
        site=Site(input_address=args.address, latitude=lat, longitude=lon, **site_kwargs),
    )
    result = await analyze(task, settings=settings)
    payload = result.model_dump()

    if args.out:
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"저장: {args.out}")

    if args.full:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"status  {result.status}")
    print(f"scope   {result.scope.area} / {result.scope.period}")
    if result.error:
        print(f"error   [{result.error.code}] {result.error.message}")
    for warning in result.warnings:
        print(f"warn    {warning}")
    if not result.data:
        return 0

    data = payload["data"]
    print(f"\n총 점포 {data['store_total']}개")
    print(
        f"업종 다양성 HHI(중분류) {data['diversity']['hhi_middle']} / "
        f"유효 업종수 {data['diversity']['effective_categories']}"
    )
    print(f"음식점 밀도 {data['restaurant_density']['value']} 개/km²")
    if data.get("franchise"):
        print(f"프랜차이즈 {data['franchise']['count']}개 ({data['franchise']['ratio']:.1%})")
    print(f"\n{'업종(중분류)':<18} {'점포수':>6} {'밀도':>10} {'LQ':>7}")
    for row in data["by_middle"][:20]:
        lq = f"{row['lq']:.2f}" if row["lq"] is not None else "-"
        print(f"{row['name']:<18} {row['count']:>6} {row['density_per_km2']:>10.1f} {lq:>7}")
    summary = data.get("summary")
    if summary:
        print()
        print("=" * 72)
        for note in summary.get("radius_notes", []):
            print(f"{note['radius_m']:>4}m : {note['text']}")
        if summary.get("overall"):
            print(f"\n종합 평가       : {summary['overall']}")
        if summary.get("concentration"):
            print(f"\n집적도·특화도 평가 : {summary['concentration']}")
        print("=" * 72)
    return 0


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
