"""서울 전체 같은 업종의 개폐업 기준값을 측정한다. 운영 상수는 자동 수정하지 않는다."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path
from pprint import pformat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.agents.business_lifecycle.client import (  # noqa: E402
    get_api_key,
    get_recent_quarters,
    normalize_row,
)
from app.agents.business_lifecycle.preprocess import _aggregate_rows  # noqa: E402
from app.config import load_environment  # noqa: E402
from app.industries.catalog import INDUSTRIES_WITHOUT_SEOUL  # noqa: E402
from app.seoul import request_json  # noqa: E402

SERVICE = "VwsmMegaStorW"  # OA-22174 서울시 상권분석서비스(점포-서울시)
PAGE_SIZE = 1000
MAX_REQUESTS = 50
AUDIT_PATH = Path(__file__).resolve().parents[1] / "cache/lifecycle_baseline_measurement.json"
FIELDS = (
    "recent_year_close_rate",
    "net_change_rate",
    "turnover_rate",
    "oldest_year_close_rate",
    "close_rate_trend",
    "avg_store_count",
    "zero_filled_sources",
    "data_complete",
    "data_status",
)


def measure(raw: list[dict], base_quarter: str, quarter_count: int) -> dict:
    quarters = set(get_recent_quarters(base_quarter=base_quarter, count=quarter_count))
    rows = []
    for row in raw:
        if str(row.get("STDR_YYQU_CD")) not in quarters:
            continue
        if str(row.get("MEGA_CD")) != "11":
            raise ValueError("서울 전체 이외의 지역이 섞였습니다.")
        normalized = normalize_row(row)
        normalized["trdar_cd"] = "11"
        rows.append(normalized)
    frame = _aggregate_rows(rows, "11", base_quarter, quarter_count)
    result = {}
    for row in frame.to_dict("records"):
        code = row["service_id"]
        if code in INDUSTRIES_WITHOUT_SEOUL:
            continue
        values = {key: row[key] for key in FIELDS}
        values["exposure"] = row["avg_store_count"] * quarter_count
        result[code] = {
            key: None if isinstance(value, float) and not math.isfinite(value) else value
            for key, value in values.items()
        }
    return result


async def run(base_quarter: str, quarter_count: int) -> None:
    get_recent_quarters(base_quarter=base_quarter, count=quarter_count)
    key = get_api_key()
    rows = []
    calls = 0
    total = None
    async with httpx.AsyncClient(timeout=20) as http:
        while total is None or len(rows) < total:
            if calls >= MAX_REQUESTS:
                raise ValueError("HTTP 50회 상한 초과")
            start = len(rows) + 1
            payload = await request_json(
                http,
                base_url="http://openapi.seoul.go.kr:8088",
                api_key=key,
                service=SERVICE,
                start=start,
                end=start + PAGE_SIZE - 1,
            )
            calls += 1
            body = payload.get(SERVICE)
            if not body or not body.get("row"):
                raise ValueError("서울 전체 점포 응답이 없거나 페이지가 불완전합니다.")
            count = int(body["list_total_count"])
            if total is not None and total != count:
                raise ValueError("조회 중 전체 행 수가 바뀌었습니다.")
            total = count
            if math.ceil(total / PAGE_SIZE) > MAX_REQUESTS:
                raise ValueError("예상 요청이 50회를 초과하므로 추가 수집을 중단합니다.")
            rows.extend(body["row"])
    if len(rows) != total:
        raise ValueError("전체 행 수와 수집 결과가 다릅니다.")
    result = await asyncio.to_thread(measure, rows, base_quarter, quarter_count)
    audit = {
        "service": SERVICE,
        "http_calls": calls,
        "total_rows": total,
        "base_quarter": base_quarter,
        "quarter_count": quarter_count,
        "values": result,
    }
    path = AUDIT_PATH
    await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(
        path.write_text, json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"# {SERVICE} · 종료 {base_quarter} · {quarter_count}분기 · HTTP {calls}회 · 전체 {total}행"
    )
    print("SEOUL_INDUSTRY_LIFECYCLE_BASELINE = " + pformat(result, sort_dicts=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-quarter", default="20262")
    parser.add_argument("--quarter-count", type=int, default=12)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    load_environment()
    try:
        asyncio.run(run(args.base_quarter, args.quarter_count))
    except Exception as exc:
        print(
            f"측정 실패: {type(exc).__name__}. 키·응답 원문은 출력하지 않습니다.", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
