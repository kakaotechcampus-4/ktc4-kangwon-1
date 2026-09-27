"""주거인구·직장인구 집계와 인구 총괄.

유동인구와 **같은 상권 집합**(`_overlapping_areas` 결과)을 쓴다. 따로 상권을 고르면 세 인구의
분모가 달라져 같은 지역인데 서로 다른 구역을 세게 된다 — 이 블록을 별도 에이전트가 아니라
유동인구 `data` 안에 두는 이유다.

**런타임에 서울시 API 를 부르지 않는다.** 두 데이터셋은 경로의 분기 필터가 먹지 않아 한 분기를
쓰려고 해도 22개 분기 전체(약 3.6만 행, 36페이지)를 받아야 했다. 분석마다 70여 번 요청이 나가
12~20초가 걸렸고, 한꺼번에 보내면 서울시 API 가 오류 응답을 주어 블록이 비는 일도 있었다.
그래서 최신 분기의 서울 전체 행만 `data/resident.csv`·`data/worker.csv` 로 동봉하고
(`examples/fetch_population_snapshot.py` 로 갱신) 여기서는 그 파일을 읽는다.
`commercial_area` 의 `data/seoul_trade_areas.csv` 와 같은 방식이다.

서울 기준선은 그 파일의 서울 전체 행에서 바로 계산한다 — 상수로 박지 않는다.

⚠️ 원자료 성질(2026-09-20 22개 분기 전수 확인): 주거인구는 2023Q4, 직장인구는 2024Q4 이후
값이 바뀌지 않았다. 분기 코드는 최신으로 오므로 팀 결정(2026-09-22)대로 서울시가 발행한
분기 그대로 쓰고 따로 표기하지 않는다.
"""

from __future__ import annotations

import csv
import functools
from pathlib import Path

from .baseline import index
from .models import AGE_BANDS, FlpopRecord, PopulationRecord, period_ko
from .schemas import PopulationBenchmark, PopulationSummary, ResidentPopulation, WorkerPopulation

RESIDENT_KIND = "REPOP"
WORKER_KIND = "WRC_POPLTN"

DATA_DIR = Path(__file__).resolve().parent / "data"
SNAPSHOT_PATHS = {RESIDENT_KIND: DATA_DIR / "resident.csv", WORKER_KIND: DATA_DIR / "worker.csv"}

# 직장/주거 비가 서울 평균의 1.5배 이상이면 직장 중심, 1/1.5 이하면 주거 중심.
COMPOSITION_RATIO = 1.5

# 사람 수라는 점만 밝힌다. "통행량과 더하지 않는다" 는 description 에 한 번만 적는다.
RESIDENT_UNIT = "count 는 명(사람 수), households 는 가구, persons_per_household 는 명/가구"
WORKER_UNIT = "count 는 명(사람 수)"


def write_snapshot(rows: list[dict], kind: str, path: Path) -> tuple[str, int]:
    """API 원자료 행 중 **최신 분기**만 골라 CSV 로 쓴다. 반환: (분기, 행 수).

    컬럼은 `PopulationRecord.columns` 만 남기고 이름은 API 그대로 둔다 — 읽을 때 같은 파서를
    쓰고, 사람이 파일을 열어도 서울시 문서와 대조할 수 있다. 상권코드 순으로 정렬해 갱신 때
    달라진 행만 diff 에 보이게 한다.
    """
    if not rows:
        raise ValueError("받은 행이 없습니다.")
    quarter = max(str(r["STDR_YYQU_CD"]) for r in rows)
    latest = sorted(
        (r for r in rows if str(r["STDR_YYQU_CD"]) == quarter), key=lambda r: str(r["TRDAR_CD"])
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PopulationRecord.columns(kind), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(latest)
    return quarter, len(latest)


def load_snapshot(kind: str, path: Path | None = None) -> list[PopulationRecord]:
    """스냅샷을 읽는다. 파일이 없거나 형식이 틀리면 예외 — 호출한 쪽이 블록을 비운다.

    동봉 파일(`path` 없음)은 **프로세스당 한 번만** 읽는다. 런타임에 바뀌지 않는 자료를 요청마다
    다시 파싱하면 이벤트 루프를 약 30ms 막는다(세 에이전트가 병렬로 도는 동안). 읽기에 실패한
    결과는 캐시되지 않으므로 파일을 넣으면 다음 요청부터 바로 반영된다.
    """
    if path is None:
        return list(_bundled(kind))
    return _read(kind, path)


@functools.cache
def _bundled(kind: str) -> tuple[PopulationRecord, ...]:
    return tuple(_read(kind, SNAPSHOT_PATHS[kind]))


def _read(kind: str, path: Path) -> list[PopulationRecord]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [PopulationRecord.from_api_row(row, kind) for row in csv.DictReader(f)]


def _age_share(records: list[PopulationRecord]) -> dict[str, float]:
    total = sum(r.total for r in records) or 1.0
    return {a: round(sum(r.by_age[a] for r in records) / total, 4) for a in AGE_BANDS}


def _persons_per_household(records: list[PopulationRecord]) -> float | None:
    households = sum(r.households or 0.0 for r in records)
    return round(sum(r.total for r in records) / households, 3) if households else None


def _percentile(value: float, seoul: list[PopulationRecord]) -> int:
    """상권 1곳당 인구가 서울 상권 중 몇 백분위인지. `seoul` 은 비지 않는다(local ⊆ seoul)."""
    below = sum(1 for r in seoul if r.total <= value)
    return round(100 * below / len(seoul))


def _benchmark(
    local: list[PopulationRecord],
    seoul: list[PopulationRecord],
    quarter: str,
    label: str,
    with_households: bool,
) -> PopulationBenchmark:
    local_share, seoul_share = _age_share(local), _age_share(seoul)
    household_index = None
    if with_households:
        mine, avg = _persons_per_household(local), _persons_per_household(seoul)
        household_index = index(mine, avg) if mine is not None and avg else None
    return PopulationBenchmark(
        unit="배수(1.0 = 서울 평균), scale_percentile 은 백분위",
        baseline=(
            f"서울 전체 상권 {label} ({period_ko(quarter)} · {len(seoul):,}곳, 가중 합계 기준)"
        ),
        age_index={a: index(local_share[a], seoul_share[a]) for a in AGE_BANDS},
        scale_percentile=_percentile(sum(r.total for r in local) / len(local), seoul),
        persons_per_household_index=household_index,
    )


def resident_block(
    seoul: list[PopulationRecord], quarter: str, main_codes: set[str]
) -> ResidentPopulation | None:
    local = [r for r in seoul if r.trdar_cd in main_codes]
    if not local:
        return None
    return ResidentPopulation(
        unit=RESIDENT_UNIT,
        share_unit="비율 (0~1)",
        period_code=quarter,
        period=period_ko(quarter),
        count=sum(r.total for r in local),
        households=sum(r.households or 0.0 for r in local),
        persons_per_household=_persons_per_household(local),
        age_share=_age_share(local),
        trade_area_count=len(main_codes),
        covered_trade_areas=len(local),
        benchmark=_benchmark(local, seoul, quarter, "주거인구", with_households=True),
    )


def worker_block(
    seoul: list[PopulationRecord], quarter: str, main_codes: set[str]
) -> WorkerPopulation | None:
    local = [r for r in seoul if r.trdar_cd in main_codes]
    if not local:
        return None
    return WorkerPopulation(
        unit=WORKER_UNIT,
        share_unit="비율 (0~1)",
        period_code=quarter,
        period=period_ko(quarter),
        count=sum(r.total for r in local),
        age_share=_age_share(local),
        trade_area_count=len(main_codes),
        covered_trade_areas=len(local),
        benchmark=_benchmark(local, seoul, quarter, "직장인구", with_households=False),
    )


def summary_block(
    flpop: list[FlpopRecord],
    days: int,
    resident: list[PopulationRecord],
    worker: list[PopulationRecord],
    main_codes: set[str],
) -> PopulationSummary:
    """세 자료가 모두 있는 상권만으로 비율을 낸다. `resident`·`worker` 는 서울 전체 행."""
    res = {r.trdar_cd: r.total for r in resident}
    wrk = {r.trdar_cd: r.total for r in worker}
    flp = {r.trdar_cd: r.total for r in flpop}
    basis = main_codes & res.keys() & wrk.keys() & flp.keys()

    residents = sum(res[c] for c in basis)
    workers = sum(wrk[c] for c in basis)
    visitors_daily = sum(flp[c] for c in basis) / days

    ratio = workers / residents if residents else None
    both = res.keys() & wrk.keys()
    seoul_res = sum(res[c] for c in both)
    seoul_ratio = sum(wrk[c] for c in both) / seoul_res if seoul_res else 0.0
    # 판정은 반올림 전 값으로 한다 — 반올림한 배수(0.667)로 비교하면 정확히 1/1.5(0.6667)인
    # 경계가 주거 중심에서 빠진다.
    raw_index = ratio / seoul_ratio if ratio is not None and seoul_ratio else None

    if raw_index is None:
        composition = "판단 불가"
    elif raw_index >= COMPOSITION_RATIO:
        composition = "직장 중심"
    elif raw_index <= 1 / COMPOSITION_RATIO:
        composition = "주거 중심"
    else:
        composition = "주거·직장 혼재"

    return PopulationSummary(
        unit=(
            "배수. visitor_multiple = 유동인구(명/일) ÷ 주거인구, "
            "worker_to_resident_index = 직장/주거 비 ÷ 서울 비"
        ),
        basis_trade_areas=len(basis),
        visitor_multiple=round(visitors_daily / residents, 3) if residents else None,
        worker_to_resident_ratio=round(ratio, 3) if ratio is not None else None,
        seoul_worker_to_resident_ratio=round(seoul_ratio, 3) if seoul_ratio else None,
        worker_to_resident_index=round(raw_index, 3) if raw_index is not None else None,
        composition=composition,
        composition_rule=(
            f"index ≥ {COMPOSITION_RATIO} 직장 중심, ≤ {1 / COMPOSITION_RATIO:.2f} 주거 중심, "
            f"그 사이 혼재 (서울 {len(both):,}곳 기준). type 과 별개"
        ),
    )
