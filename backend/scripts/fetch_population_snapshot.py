"""주거인구·직장인구 최신 분기를 CSV 로 받는다. 서울시가 값을 갱신하면 다시 돌린다.

받는 것은 서울 열린데이터광장 상권분석서비스 두 개다.

- 상주인구-상권 `VwsmTrdarRepopQq` (OA-15584) → `data/resident.csv`
- 직장인구-상권 `VwsmTrdarWrcPopltnQq` (OA-15569) → `data/worker.csv`

두 서비스는 경로의 분기 필터가 먹지 않아 22개 분기 전체(각 약 3.6만 행)를 받은 뒤 최신 분기
(서울 약 1,640행)만 남긴다. 결과를 패키지에 동봉하므로 **유동인구 에이전트는 런타임에 이 두
API 를 부르지 않는다**(`floating_population/population.py`). 값이 연 1회도 채 바뀌지 않는
자료라(주거 2023Q4, 직장 2024Q4 이후 동일) 분기마다 돌릴 필요는 없다 — 파일의 분기가 유동인구
분기보다 뒤처지면 에이전트가 warnings 로 알린다.

    python scripts/fetch_population_snapshot.py

키는 유동인구와 같은 `FLOATING_POPULATION_API_KEY`(backend/.env)다.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.floating_population.client import SeoulOpenDataClient  # noqa: E402
from app.agents.floating_population.config import (  # noqa: E402
    RESIDENT_SERVICE,
    WORKER_SERVICE,
    Settings,
)
from app.agents.floating_population.population import (  # noqa: E402
    RESIDENT_KIND,
    SNAPSHOT_PATHS,
    WORKER_KIND,
    write_snapshot,
)
from app.config import load_environment  # noqa: E402
from app.seoul import SeoulOpenApiError  # noqa: E402


class SnapshotClient(SeoulOpenDataClient):
    """스냅샷 생성 때만 전체 분기를 조회합니다."""

    page_concurrency = 8
    page_retries = 2

    async def fetch_all_rows(self, service: str) -> list[dict]:
        """분기 필터가 먹지 않는 서비스(주거·직장인구)의 **전 분기·서울 전체** 원자료 행.

        스냅샷 CSV 를 만들 때만 쓴다(`scripts/fetch_population_snapshot.py`) — 에이전트는 부르지
        않는다. 두 서비스는 경로 끝에 분기를 붙여도 걸러지지 않고(`20262` 를 붙여도 35,908행
        전부) 분기순 정렬도 아니라 끝까지 받아야 한다.

        첫 페이지로 총 행 수를 안 뒤 나머지를 동시에 받되 **동시 요청을 `page_concurrency` 로
        묶고 페이지마다 재시도한다.** 60여 개를 한꺼번에 보내면 서울시 API 가 JSON 이 아닌 오류
        응답을 돌려주고, 8개로 묶으면 재시도 없이 다 받아졌다(2026-09-26 확인).
        """
        size = self.settings.page_size
        retries = self.page_retries
        limit = asyncio.Semaphore(self.page_concurrency)

        async def page(start: int) -> dict:
            for attempt in range(retries + 1):
                try:
                    async with limit:
                        return await self._get_page(service, start, start + size - 1)
                except (SeoulOpenApiError, httpx.HTTPError, ValueError):
                    if attempt == retries:
                        raise
                await asyncio.sleep(1 + attempt)  # 기다리는 동안은 동시 슬롯을 비워 둔다
            raise AssertionError("도달하지 않는다")

        first = await page(1)
        # 상한을 두지 않는다 — 행이 분기순이 아니라 잘라내면 최신 분기 행이 무작위로 빠진다.
        total = int(first.get("list_total_count", 0))
        rest = await asyncio.gather(*(page(s) for s in range(size + 1, total + 1, size)))
        return [r for body in (first, *rest) for r in body.get("row", [])]


async def fetch() -> None:
    settings = Settings.from_env()
    targets = (
        ("주거인구", RESIDENT_KIND, RESIDENT_SERVICE),
        ("직장인구", WORKER_KIND, WORKER_SERVICE),
    )
    # 둘 다 받은 뒤에 쓴다 — 하나만 새로 쓰고 실패하면 두 파일의 분기가 어긋난 채 남는다.
    async with SnapshotClient(settings) as client:
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
