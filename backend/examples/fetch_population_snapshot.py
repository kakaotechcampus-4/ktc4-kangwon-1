"""주거인구·직장인구 최신 분기를 CSV 로 받는다. 서울시가 값을 갱신하면 다시 돌린다.

받는 것은 서울 열린데이터광장 상권분석서비스 두 개다.

- 상주인구-상권 `VwsmTrdarRepopQq` (OA-15584) → `data/resident.csv`
- 직장인구-상권 `VwsmTrdarWrcPopltnQq` (OA-15569) → `data/worker.csv`

두 서비스는 경로의 분기 필터가 먹지 않아 22개 분기 전체(각 약 3.6만 행)를 받은 뒤 최신 분기
(서울 약 1,640행)만 남긴다. 결과를 패키지에 동봉하므로 **유동인구 에이전트는 런타임에 이 두
API 를 부르지 않는다**(`floating_population/population.py`). 값이 연 1회도 채 바뀌지 않는
자료라(주거 2023Q4, 직장 2024Q4 이후 동일) 분기마다 돌릴 필요는 없다 — 파일의 분기가 유동인구
분기보다 뒤처지면 에이전트가 warnings 로 알린다.

    python examples/fetch_population_snapshot.py

키는 유동인구와 같은 `FLOATING_POPULATION_API_KEY`(backend/.env)다.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.floating_population.client import SeoulOpenDataClient  # noqa: E402
from app.agents.floating_population.config import Settings  # noqa: E402
from app.agents.floating_population.population import (  # noqa: E402
    RESIDENT_KIND,
    SNAPSHOT_PATHS,
    WORKER_KIND,
    write_snapshot,
)
from app.config import load_environment  # noqa: E402


async def fetch() -> None:
    settings = Settings.from_env()
    targets = (
        ("주거인구", RESIDENT_KIND, settings.resident_service),
        ("직장인구", WORKER_KIND, settings.worker_service),
    )
    # 둘 다 받은 뒤에 쓴다 — 하나만 새로 쓰고 실패하면 두 파일의 분기가 어긋난 채 남는다.
    async with SeoulOpenDataClient(settings) as client:
        fetched = [await client.fetch_all_rows(service) for _, _, service in targets]
    for (label, kind, _), rows in zip(targets, fetched, strict=True):
        path = SNAPSHOT_PATHS[kind]
        quarter, count = write_snapshot(rows, kind, path)
        print(f"{label}: 원자료 {len(rows):,}행 중 {quarter} {count:,}행 → {path}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    load_environment()
    asyncio.run(fetch())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
