"""상권 경쟁 분석 에이전트를 실행합니다."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from app.address import GeocodeError, resolve_site, split_detail
from app.agents.commercial_area import analyze
from app.agents.commercial_area.config import Settings, load_dotenv_if_present
from app.schemas import AnalysisTask, Site


async def run() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--address")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--radius", type=int)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    # 기본 주소를 두면 좌표만 준 실행에서 엉뚱한 주소 라벨이 붙는다. 라벨과 좌표가 어긋난
    # 결과가 조용히 나가는 것보다 여기서 멈추는 편이 낫다.
    if not args.address:
        parser.error("--address 가 필요합니다. 좌표를 직접 줄 때도 함께 주세요.")

    load_dotenv_if_present()
    overrides = {"analysis_radius_m": args.radius} if args.radius else {}
    settings = Settings.from_env(**overrides)

    if args.lat is None or args.lon is None:
        try:
            site = await resolve_site(args.address)
        except GeocodeError as exc:
            print(f"주소를 좌표로 바꾸지 못했습니다: {exc}")
            return 1
        print(f"카카오 주소 확인 → {site.latitude}, {site.longitude}")
        if site.detail_address:
            print(f"          분리한 상세주소: {site.detail_address}")
        if site.road_address:
            print(f"          {site.road_address}")
    else:
        lat, lon = args.lat, args.lon
        # 좌표를 직접 주면 지오코딩을 건너뛰는데, Site 는 도로명·지번 중 하나를 요구한다.
        # 입력 주소에서 상세주소만 떼어 기본 주소로 쓴다.
        base, detail = split_detail(args.address)
        site = Site(
            input_address=args.address,
            road_address=base,
            detail_address=detail,
            latitude=lat,
            longitude=lon,
        )
        print(f"좌표 직접 입력  {lat}, {lon}")
        if detail:
            print(f"          분리한 상세주소: {detail}")

    task = AnalysisTask(
        request_id=str(uuid.uuid4()),
        site=site,
        radius_m=settings.analysis_radius_m,
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
