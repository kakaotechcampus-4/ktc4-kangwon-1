"""서울 전체 상권 기준선을 측정해 검토용 Python 상수를 출력합니다.

기본은 최신 분기이며 --quarter 20262로 과거 기준선을 재현할 수 있습니다.
최신 분기가 다르면 20262도 같은 실행에서 조회해 기존 상수를 검증합니다.
파일과 운영 상수는 수정하지 않습니다. API 키는 backend/.env에서 읽습니다.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import math
import sys
from pathlib import Path
from pprint import pformat
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.floating_population import baseline  # noqa: E402
from app.agents.floating_population.client import SeoulOpenDataClient  # noqa: E402
from app.agents.floating_population.metrics import _aggregate  # noqa: E402
from app.agents.floating_population.models import (  # noqa: E402
    AGE_BANDS,
    DAYS,
    TIME_BANDS,
    FlpopRecord,
    quarter_days,
)
from app.config import load_environment  # noqa: E402

REFERENCE_QUARTER = "20262"
PERCENTILES = tuple(range(5, 100, 5))


class BaselineClient(SeoulOpenDataClient):
    async def fetch_quarter(self, quarter: str) -> list[FlpopRecord]:
        """전체 페이지 수와 고유 상권·분기를 검증합니다."""
        size = self.settings.page_size
        service = self.settings.flpop_service
        first = await self._get_page(service, 1, size, extra=quarter)
        total = int(first.get("list_total_count", 0))
        if total <= 0 or total > size * self.settings.flpop_max_pages:
            raise ValueError("서울 전체 분기 자료가 없거나 페이지 상한을 초과했습니다.")
        rows = list(first.get("row", []))
        for start in range(size + 1, total + 1, size):
            body = await self._get_page(service, start, start + size - 1, extra=quarter)
            if int(body.get("list_total_count", 0)) != total:
                raise ValueError("페이지 사이에 전체 행 수가 바뀌었습니다.")
            rows.extend(body.get("row", []))
        if len(rows) != total:
            raise ValueError("전체 행 수와 수집 행 수가 다릅니다.")
        columns = [
            "TOT_FLPOP_CO",
            "ML_FLPOP_CO",
            "FML_FLPOP_CO",
            *(f"TMZON_{band}_FLPOP_CO" for band in TIME_BANDS),
            *(f"AGRDE_{age}_FLPOP_CO" for age in AGE_BANDS[:-1]),
            "AGRDE_60_ABOVE_FLPOP_CO",
            "MON_FLPOP_CO",
            "TUES_FLPOP_CO",
            "WED_FLPOP_CO",
            "THUR_FLPOP_CO",
            "FRI_FLPOP_CO",
            "SAT_FLPOP_CO",
            "SUN_FLPOP_CO",
        ]
        for row in rows:
            if any(row.get(key) in (None, "") for key in columns):
                raise ValueError("기준선 측정에 필요한 원자료 칼럼이 누락되었습니다.")
        return [FlpopRecord.from_api_row(row) for row in rows]


def quantiles(values: list[float]) -> dict[int, float]:
    """선형 보간 표본 분위수이며 출력 반올림은 마지막에만 합니다."""
    series = pd.Series(values, dtype=float)
    return {p: round(float(series.quantile(p / 100)), 1) for p in PERCENTILES}


def measure(
    records: list[FlpopRecord],
    quarter: str,
    patterns: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    if not records or len({r.trdar_cd for r in records}) != len(records):
        raise ValueError("상권 자료가 비었거나 중복되었습니다.")
    for row in records:
        values = [
            row.total,
            row.male,
            row.female,
            *row.by_age.values(),
            *row.by_time.values(),
            *row.by_day.values(),
        ]
        if row.stdr_yyqu_cd != quarter or any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("분기가 섞였거나 음수·비유한 수치가 있습니다.")
        if (
            set(row.by_time) != set(TIME_BANDS)
            or set(row.by_age) != set(AGE_BANDS)
            or set(row.by_day) != set(DAYS)
        ):
            raise ValueError("집계에 필요한 분포 항목이 누락되었습니다.")
    if (
        sum(r.total for r in records) <= 0
        or sum(sum(r.by_day[d] for d in DAYS[:5]) for r in records) <= 0
    ):
        raise ValueError("기준 분포의 분모가 0입니다.")
    patterns = patterns or {}
    if any(
        not bands or len(set(bands)) != len(bands) or not set(bands) <= set(TIME_BANDS)
        for bands in patterns.values()
    ):
        raise ValueError("패턴에 잘못된 시간대가 있습니다.")
    population = _aggregate(records, quarter)
    return {
        "AGE_SHARE_AVG": population.age_share,
        "TIME_PER_HOUR_SHARE_AVG": population.time_per_hour_share,
        "WEEKEND_TO_WEEKDAY_AVG": population.weekend_to_weekday_ratio,
        "SCALE_PERCENTILES": quantiles([r.total for r in records]),
        "DAILY_TOTAL_PERCENTILES": quantiles([r.total / quarter_days(quarter) for r in records]),
        "PATTERN_DAILY_PERCENTILES": {
            name: quantiles(
                [sum(r.by_time[band] for band in bands) / quarter_days(quarter) for r in records]
            )
            for name, bands in patterns.items()
        },
        "PATTERN_TIME_PER_HOUR_SHARE_AVG": {
            name: round(sum(population.time_per_hour_share[band] for band in bands), 4)
            for name, bands in patterns.items()
        },
        "TIME_BAND_DAILY_PERCENTILES": {
            band: quantiles([r.by_time[band] / quarter_days(quarter) for r in records])
            for band in TIME_BANDS
        },
    }


def reference_matches(result: dict[str, Any]) -> dict[str, bool]:
    matches = {}
    for name in (
        "AGE_SHARE_AVG",
        "TIME_PER_HOUR_SHARE_AVG",
        "WEEKEND_TO_WEEKDAY_AVG",
        "SCALE_PERCENTILES",
    ):
        actual, expected = result[name], getattr(baseline, name)
        tolerance = 0.5 if name == "SCALE_PERCENTILES" else 0.00005
        if isinstance(expected, dict):
            matches[name] = actual.keys() == expected.keys() and all(
                abs(actual[key] - value) <= tolerance for key, value in expected.items()
            )
        else:
            matches[name] = abs(actual - expected) <= tolerance
    return matches


def read_patterns() -> dict[str, tuple[str, ...]]:
    """측정 스크립트에서만 승인된 시간대 열을 읽습니다. 새 프로필 열은 사용하지 않습니다."""
    path = Path(__file__).resolve().parents[1] / "app/industries/data/industry_profile.csv"
    patterns: dict[str, tuple[str, ...]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["reviewed"] != "true":
                raise ValueError("시간대 검토가 완료되지 않은 업종이 있습니다.")
            name = row["pattern"]
            if name == "무관":
                continue
            bands = tuple(row["primary_bands"].split(";"))
            if name in patterns and patterns[name] != bands:
                raise ValueError("같은 패턴의 시간대가 서로 다릅니다.")
            patterns[name] = bands
    return patterns


async def run(quarter: str | None) -> None:
    patterns = read_patterns()
    async with BaselineClient() as client:
        latest = quarter or await client.latest_quarter()
        current = await client.fetch_quarter(latest)
        reference = (
            current
            if latest == REFERENCE_QUARTER
            else await client.fetch_quarter(REFERENCE_QUARTER)
        )
    reference_result = measure(reference, REFERENCE_QUARTER, patterns)
    result = reference_result if latest == REFERENCE_QUARTER else measure(current, latest, patterns)
    print("# 측정값은 검토용입니다. 이 스크립트는 파일이나 운영 상수를 수정하지 않습니다.")
    print(f"MEASURED_QUARTER = {latest!r}")
    print(f"TRADE_AREA_COUNT = {len(current)}")
    print(f"REFERENCE_TRADE_AREA_COUNT = {len(reference)}")
    print(f"REFERENCE_TOTAL = {sum(r.total for r in reference)!r}")
    print(f"REFERENCE_MATCHES = {pformat(reference_matches(reference_result))}")
    for name, value in result.items():
        print(f"{name} = {pformat(value, sort_dicts=False)}")
    print(f"REFERENCE_MEASUREMENTS = {pformat(reference_result, sort_dicts=False)}")
    if latest == REFERENCE_QUARTER:
        comparison = {
            p: {
                "legacy_quarter_total": baseline.SCALE_PERCENTILES[p],
                "daily_times_days": round(value * quarter_days(latest), 1),
                "difference": round(
                    value * quarter_days(latest) - baseline.SCALE_PERCENTILES[p], 1
                ),
            }
            for p, value in result["DAILY_TOTAL_PERCENTILES"].items()
        }
        print(f"DAILY_TOTAL_VS_LEGACY = {pformat(comparison, sort_dicts=False)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quarter", help="기준년분기 5자리. 미지정이면 최신 분기를 탐침합니다.")
    args = parser.parse_args()
    if args.quarter and (
        len(args.quarter) != 5 or not args.quarter.isdigit() or args.quarter[-1] not in "1234"
    ):
        parser.error("분기는 20262처럼 연도 4자리와 분기 1~4로 지정합니다.")
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    load_environment()
    try:
        asyncio.run(run(args.quarter))
    except Exception as exc:
        # HTTP 예외 원문에는 키가 포함된 URL이 있을 수 있습니다.
        print(
            f"기준선 측정 실패: {type(exc).__name__}. 상수는 변경하지 않았습니다.", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
