"""운영 가중치·등급 경계를 유지하며 과거 D·C1·S 기준선만 일치시킵니다."""

import json
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.agentic import scoring
from app.agents.floating_population import baseline as population_baseline
from app.agents.floating_population.models import FlpopRecord
from app.db.connection import readonly
from backtest.licensing import sha256
from backtest.past_data import CUTOFF, public_rows
from backtest.temporal_data import inventory, one_version
from scripts.measure_flpop_baseline import measure as measure_population
from scripts.measure_flpop_baseline import read_patterns
from scripts.measure_lifecycle_baseline import measure as measure_lifecycle


def rows_for(data: Path, version: dict) -> list[dict]:
    columns = json.loads(version["columns_json"])
    source = version["source"]
    if source not in ("floating", "resident", "worker"):
        raise ValueError("인구 기준선에 사용할 원천이 아닙니다.")
    with readonly(data) as db:
        return [
            dict(zip(columns, json.loads(r[0]), strict=True))
            for r in db.execute(
                f"SELECT payload FROM {source} WHERE version_id=?", (version["version_id"],)
            )
        ]


def population_values(rows: list[dict], quarter: str) -> dict:
    records = [FlpopRecord.from_api_row(row) for row in rows]
    values = measure_population(records, quarter, read_patterns())
    # 운영의 분기 총량 분포만 nearest이며, 일평균·시간대·패턴 분포는 linear입니다.
    totals = pd.Series([r.total for r in records], dtype=float)
    values["SCALE_PERCENTILES"] = {
        p: float(totals.quantile(p / 100, interpolation="nearest")) for p in range(5, 100, 5)
    }
    return values


def same_values(actual, expected, tolerance=0.0001) -> bool:
    if isinstance(actual, dict):
        return (
            isinstance(expected, dict)
            and actual.keys() == expected.keys()
            and all(same_values(v, expected[k], tolerance) for k, v in actual.items())
        )
    return abs(actual - expected) <= tolerance


def build(data: Path, current: Path, source: Path, competition: Path) -> dict:
    versions = inventory(data)
    floating = rows_for(data, one_version(versions, "floating", CUTOFF))
    past_values = population_values(floating, CUTOFF)
    # 측정 방법 변경과 시점 변경이 섞이지 않도록 같은 함수로 현재 운영 상수를 재현합니다.
    current_rows = rows_for(current, one_version(inventory(current), "floating", "20262"))
    reference = population_values(current_rows, "20262")
    audit = {
        name: same_values(
            value, getattr(population_baseline, name), 0.11 if "PERCENTILES" in name else 0.0001
        )
        for name, value in reference.items()
    }
    if not all(audit.values()):
        raise ValueError("현재 인구 기준선 측정 방법이 재현되지 않았습니다: " + str(audit))
    from app.agents.business_lifecycle.client import get_recent_quarters

    quarters = get_recent_quarters(CUTOFF, 12)
    city = [row for q in quarters for row in public_rows(source, "city", q)]
    if any(len(public_rows(source, "city", q)) != 100 for q in quarters):
        raise ValueError("서울 전체 기준선 원문의 100업종·12분기가 불완전합니다.")
    lifecycle = measure_lifecycle(city, CUTOFF, 12)
    if len(lifecycle) != 45 or any(
        not v["data_complete"] or v["zero_filled_sources"] for v in lifecycle.values()
    ):
        raise ValueError("서울 전체 S 기준선의 대응 업종이 불완전합니다.")
    density = json.loads((competition / "results.json").read_text(encoding="utf-8"))
    if density["metadata"]["reference_quarter"] != CUTOFF:
        raise ValueError("경쟁 기준선 시점이 다릅니다.")
    return {
        "cutoff": CUTOFF,
        "quarter_count": 12,
        "population": past_values,
        "density": {
            c: {int(p): value for p, value in v.items()} for c, v in density["baseline"].items()
        },
        "lifecycle": lifecycle,
        "current_population_reproduction": audit,
        "source_population_n": len(floating),
        "source_city_n": len(city),
        "source_city_quarters": quarters,
        "competition_result_sha256": sha256(competition / "results.json"),
        "code_sha256": sha256(Path(__file__)),
    }


@contextmanager
def calibrated(values: dict):
    """검증 프로세스에서만 적용하고 끝나면 운영 모듈의 원래 값으로 복원합니다."""
    with ExitStack() as stack:
        for name, value in values["population"].items():
            stack.enter_context(patch.object(population_baseline, name, value))
        stack.enter_context(
            patch.object(
                population_baseline,
                "BASELINE_LABEL",
                "서울 전체 상권 (2025년 2분기 · 과거 검증 기준)",
            )
        )
        stack.enter_context(
            patch.object(scoring, "SEOUL_INDUSTRY_DENSITY_PERCENTILES", values["density"])
        )
        stack.enter_context(
            patch.object(scoring, "SEOUL_INDUSTRY_LIFECYCLE_BASELINE", values["lifecycle"])
        )
        stack.enter_context(patch.object(scoring, "BASELINE_BASE_QUARTER", values["cutoff"]))
        stack.enter_context(
            patch.object(scoring, "BASELINE_QUARTER_COUNT", values["quarter_count"])
        )
        yield
