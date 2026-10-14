"""서울 자료를 요청과 분리해 적재합니다. 실패하면 이전 release를 유지합니다.

예: python scripts/refresh_local_data.py --quarter 20262 --seoul-csv <서울 CSV>
--source resident --api 로 상주 전체 API를 받고 필요한 최신 분기를 적재합니다.
--dry-run 은 파일만 검증하고 API/자료 DB를 변경하지 않습니다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.business_lifecycle.config import Settings as LifecycleSettings  # noqa: E402
from app.agents.floating_population.config import (  # noqa: E402
    FLPOP_SERVICE,
    RESIDENT_SERVICE,
    WORKER_SERVICE,
)
from app.config import BACKEND_DIR, load_environment  # noqa: E402
from app.local_data.database import (  # noqa: E402
    SOURCES,
    DataValidationError,
    LocalDataDB,
    default_path,
)
from app.local_data.refresh import (  # noqa: E402
    collect_pages,
    csv_rows,
    file_hash,
    normalize,
    rows_hash,
    shape_hash,
    shape_rows,
    store_rows,
)
from app.seoul import previous_quarter, request_json  # noqa: E402
from scripts.build_density_baseline import CSV_FIELDS  # noqa: E402

SERVICES = {
    "lifecycle": "VwsmTrdarStorQq",
    "floating": FLPOP_SERVICE,
    "resident": RESIDENT_SERVICE,
    "worker": WORKER_SERVICE,
}


def quarters(latest: str, count: int) -> list[str]:
    previous_quarter(latest)
    result = [latest]
    for _ in range(count - 1):
        result.append(previous_quarter(result[-1]))
    return result


async def refresh(args, db: LocalDataDB) -> list[dict]:
    selected = args.source or list(SOURCES)
    versions = []
    report = []
    checkpoints = []
    async with httpx.AsyncClient(timeout=30) as http:
        for source in selected:
            started = time.monotonic()
            requests = 0
            count = args.quarters or (
                12 if source == "lifecycle" else 5 if source == "floating" else 1
            )
            needed = quarters(args.quarter, count)
            if source in ("stores", "areas", "resident", "worker") and not (
                args.api and source in ("resident", "worker")
            ):
                path = (
                    args.seoul_csv
                    if source == "stores"
                    else args.shp
                    if source == "areas"
                    else BACKEND_DIR / f"app/agents/floating_population/data/{source}.csv"
                )
                if path is None:
                    raise DataValidationError("--seoul-csv 에 서울 CSV 경로를 지정하세요.")
                if source == "stores":
                    if path.resolve().is_relative_to(BACKEND_DIR.parent):
                        raise DataValidationError("상가 원문 CSV는 저장소 밖에 두세요.")
                    version = await asyncio.to_thread(
                        db.stage,
                        source,
                        args.quarter,
                        store_rows(path, CSV_FIELDS),
                        await asyncio.to_thread(file_hash, [path]),
                    )
                    await asyncio.to_thread(db.validate_seoul_stores, version)
                elif source == "areas":
                    version = await asyncio.to_thread(
                        db.stage,
                        source,
                        "",
                        shape_rows(path),
                        await asyncio.to_thread(shape_hash, path),
                    )
                else:
                    rows = await asyncio.to_thread(lambda path=path: list(csv_rows(path)))
                    periods = {str(row["STDR_YYQU_CD"]) for row in rows}
                    if len(periods) != 1:
                        raise DataValidationError("동봉 인구 CSV의 분기는 하나여야 합니다.")
                    period = periods.pop()
                    version = await asyncio.to_thread(
                        db.stage,
                        source,
                        period,
                        (normalize(source, row, period) for row in rows),
                        await asyncio.to_thread(file_hash, [path]),
                    )
                versions.append(version)
                total_rows = (await asyncio.to_thread(db.version, version))["row_count"]
            else:
                if args.dry_run:
                    item = {"source": source, "status": "API 필요·dry-run 미호출"}
                    report.append(item)
                    print(json.dumps(item, ensure_ascii=False), flush=True)
                    continue
                key = (
                    (os.getenv("BUSINESS_LIFECYCLE_API_KEY") or os.getenv("SEOUL_OPEN_API_KEY"))
                    if source == "lifecycle"
                    else os.getenv("FLOATING_POPULATION_API_KEY")
                )
                if not key:
                    raise DataValidationError("서울 API 키 설정이 없습니다.")
                total_rows = 0
                for period in needed if source in ("lifecycle", "floating") else [None]:
                    checkpoint = f"v1:{SERVICES[source]}:{period or 'all'}"
                    checkpoints.append(checkpoint)

                    async def fetch(
                        start, end, service=SERVICES[source], extra=period, api_key=key
                    ):
                        payload = await request_json(
                            http,
                            base_url="http://openapi.seoul.go.kr:8088",
                            api_key=api_key,
                            service=service,
                            start=start,
                            end=end,
                            extra=extra,
                        )
                        body = payload.get(service)
                        if not body:
                            raise DataValidationError("서울 API 서비스 자료 없음")
                        return body

                    rows, used = await collect_pages(db, checkpoint, fetch)
                    requests += used
                    periods = [period] if period else needed
                    for q in periods:
                        filtered = [row for row in rows if str(row.get("STDR_YYQU_CD")) == q]
                        if period and len(filtered) != len(rows):
                            raise DataValidationError(
                                "분기 전체 조회에 다른 분기 자료가 섞였습니다."
                            )
                        version = await asyncio.to_thread(
                            db.stage,
                            source,
                            q,
                            (normalize(source, row, q) for row in filtered),
                            await asyncio.to_thread(rows_hash, filtered),
                        )
                        versions.append(version)
                        total_rows += len(filtered)
            item = {
                "source": source,
                "rows": total_rows,
                "http": requests,
                "seconds": round(time.monotonic() - started, 2),
            }
            report.append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)
    if args.dry_run:
        return report
    old = await asyncio.to_thread(db.active_versions)
    unchanged = []
    for vid in old:
        meta = await asyncio.to_thread(db.version, vid)
        if meta["source"] not in selected:
            unchanged.append(vid)
    await asyncio.to_thread(db.activate, unchanged + versions)
    await asyncio.to_thread(db.clear_pages, checkpoints)
    if not args.no_vacuum:
        before, after = await asyncio.to_thread(db.vacuum)
        print(json.dumps({"vacuum_before": before, "vacuum_after": after}), flush=True)
    return report


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", choices=SOURCES, action="append")
    p.add_argument("--quarter", default="20262")
    p.add_argument("--quarters", type=int, choices=range(1, 25))
    p.add_argument("--seoul-csv", type=Path)
    p.add_argument("--shp", type=Path, default=LifecycleSettings.from_env().area_shape_path)
    p.add_argument("--db", type=Path, default=default_path())
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-vacuum", action="store_true")
    p.add_argument("--api", action="store_true", help="상주/직장은 전체 API에서 선택 분기를 적재")
    return p


def main() -> int:
    load_environment()
    args = parser().parse_args()
    if args.db.resolve().is_relative_to(BACKEND_DIR.parent):
        raise DataValidationError("자료 DB는 저장소 밖 경로로 지정하세요.")
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory() as temp:
            db = LocalDataDB(Path(temp) / "dryrun.sqlite3" if args.dry_run else args.db)
            asyncio.run(refresh(args, db))
            print(
                json.dumps(
                    {
                        "dry_run": args.dry_run,
                        "db_bytes": db.path.stat().st_size,
                        "seconds": round(time.monotonic() - started, 2),
                    },
                    ensure_ascii=False,
                )
            )
    except Exception as exc:
        # HTTP 예외의 URL·키를 출력하지 않습니다. 체크포인트는 다음 실행에 남습니다.
        print(
            json.dumps(
                {
                    "failed": type(exc).__name__,
                    "message": str(exc)
                    if isinstance(exc, DataValidationError)
                    else "적재 실패·활성 버전 유지",
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
