import argparse
import asyncio
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np

from app.agents.floating_population import baseline, classify
from app.agents.floating_population.client import SeoulOpenDataClient
from app.agents.floating_population.config import Settings as PopulationSettings
from app.agents.floating_population.models import (
    AGE_BANDS,
    TIME_BAND_HOURS,
    TIME_BANDS,
    WEEKDAYS,
    WEEKEND,
    FlpopRecord,
    missing_fields,
    period_ko,
)
from app.config import load_environment

DATA_DIR = Path(__file__).resolve().parent / "data"
PERCENTILES = range(5, 100, 5)


def aggregate(records: list[FlpopRecord], quarter: str) -> dict[str, Any]:
    if not records:
        raise ValueError(f"{quarter} 유동인구 행이 없습니다.")
    incomplete = [r.trdar_cd for r in records if missing_fields(r)]
    if incomplete:
        raise ValueError(f"{quarter} 유동인구 결측 상권 {len(incomplete)}곳: {incomplete[:5]}")
    totals = [float(r.total or 0.0) for r in records]
    total = sum(totals)
    by_age = {a: sum(r.by_age[a] or 0.0 for r in records) for a in AGE_BANDS}
    per_hour = {
        b: sum(r.by_time[b] or 0.0 for r in records) / TIME_BAND_HOURS[b] for b in TIME_BANDS
    }
    hours = sum(per_hour.values())
    weekday = sum(r.by_day[d] or 0.0 for r in records for d in WEEKDAYS) / len(WEEKDAYS)
    weekend = sum(r.by_day[d] or 0.0 for r in records for d in WEEKEND) / len(WEEKEND)
    share = {a: by_age[a] / total for a in AGE_BANDS}
    weekend_ratio = weekend / weekday
    return {
        "quarter": quarter,
        "area_count": len(records),
        "total": int(round(total)),
        "AGE_SHARE_AVG": {a: round(share[a], 4) for a in AGE_BANDS},
        "TIME_PER_HOUR_SHARE_AVG": {b: round(per_hour[b] / hours, 4) for b in TIME_BANDS},
        "WEEKEND_TO_WEEKDAY_AVG": round(weekend_ratio, 4),
        "SCALE_PERCENTILES": {
            str(p): float(np.percentile(totals, p, method="nearest")) for p in PERCENTILES
        },
        "SEOUL_AVG": {
            "age_10": round(share["10"], 3),
            "age_20": round(share["20"], 3),
            "age_30_40": round(share["30"] + share["40"], 3),
            "age_50_60": round(share["50"] + share["60"], 3),
            "weekend_to_weekday": round(weekend_ratio, 3),
        },
    }


async def measure(quarter: str, client: SeoulOpenDataClient) -> dict:
    rows = await client._fetch_all(
        client.settings.flpop_service, client.settings.flpop_max_pages, extra=quarter
    )
    records = [FlpopRecord.from_api_row(r) for r in rows]
    others = {r.stdr_yyqu_cd for r in records} - {quarter}
    if others:
        raise ValueError(f"{quarter}가 아닌 분기 행이 섞였습니다: {sorted(others)}")
    return aggregate(records, quarter)


def path_for(quarter: str, folder: Path = DATA_DIR) -> Path:
    return folder / f"population_baseline_{quarter}.json"


def load(quarter: str, folder: Path = DATA_DIR) -> dict:
    path = path_for(quarter, folder)
    if not path.exists():
        raise FileNotFoundError(
            f"{quarter} 유동인구 서울 기준선 파일이 없습니다: {path}. "
            f"python -m backtest.population_baseline --quarter {quarter} --out {path} "
            "로 먼저 측정하세요."
        )
    values = json.loads(path.read_text(encoding="utf-8"))
    if values.get("quarter") != quarter:
        raise ValueError(f"{path}의 분기가 {quarter}가 아닙니다.")
    return values


def label(values: dict) -> str:
    return f"서울 전체 상권 평균 ({period_ko(values['quarter'])} · {values['area_count']:,}곳)"


@contextmanager
def as_of(values: dict) -> Iterator[None]:
    seoul = dict(values["SEOUL_AVG"])
    with (
        patch.multiple(
            baseline,
            BASELINE_LABEL=label(values),
            AGE_SHARE_AVG=dict(values["AGE_SHARE_AVG"]),
            TIME_PER_HOUR_SHARE_AVG=dict(values["TIME_PER_HOUR_SHARE_AVG"]),
            WEEKEND_TO_WEEKDAY_AVG=values["WEEKEND_TO_WEEKDAY_AVG"],
            SCALE_PERCENTILES={int(p): v for p, v in values["SCALE_PERCENTILES"].items()},
        ),
        patch.multiple(
            classify,
            SEOUL_AVG=seoul,
            STUDENT_MIN=seoul["age_10"] + classify.MARGIN,
            LEISURE_MIN=seoul["age_20"] + classify.MARGIN,
            OFFICE_MIN=seoul["age_30_40"] + classify.MARGIN,
            RESIDENT_MIN=seoul["age_50_60"] + classify.MARGIN,
        ),
    ):
        yield


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quarter", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    load_environment()
    settings = PopulationSettings.from_env()

    async def go() -> dict:
        async with SeoulOpenDataClient(settings) as client:
            return await measure(args.quarter, client)

    try:
        values = asyncio.run(go())
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        if settings.api_key:
            message = message.replace(settings.api_key, "***")
        print(message, file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{args.quarter}: 상권 {values['area_count']}곳 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
