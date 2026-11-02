"""기준 시점까지의 자료로 현재 코드 90점을 다시 매기고, 이후 4분기 개폐업으로 추천을 채점합니다.

채점 함수(scoring.evaluate)와 문항·등급 경계는 바꾸지 않습니다.
기준 시점에 알 수 없던 값만 바꿉니다.
- 개폐업: 기준 시점까지 8분기(서비스는 12분기). 서울 기준선도 같은 8분기 상권 합산으로 다시 계산
- 유동인구: 기준 분기 한 분기. 전년 동기 자료가 없어 D4는 미확인
- 점포·상주·직장: 2026Q2 한 시점만 있어 service 방식에 그대로 사용(근사)
  strict 방식은 이 셋을 쓰지 않고 C1을 미확인, D3를 유동 연령 대체로 채점
- 지도 시설·규제·공간 조건·L은 조회하지 않음(offline.py와 동일)
LLM·주소 변환·지도·규제 호출은 0회이며 네트워크를 차단하고 자료 DB는 읽기 전용으로 엽니다.
"""

import argparse
import hashlib
import json
import math
import random
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from app.agentic import scoring
from app.agents.business_lifecycle.baseline import SEOUL_INDUSTRY_LIFECYCLE_BASELINE
from app.agents.business_lifecycle.client import get_recent_quarters, normalize_row
from app.agents.business_lifecycle.preprocess import aggregate_rows
from app.geo import to_epsg5181
from app.industries.catalog import INDUSTRIES_WITHOUT_SEOUL
from app.local_data.adapter import LocalAdapter
from app.schemas import AnalysisTask, Site
from backtest import forward_metrics
from backtest.offline import block_network

CUTOFF = "20252"
PAST_N = 8
FUTURE_N = 4
# 서비스 개폐업 문항과 같은 최소 노출량(분기 점포 수 합계)입니다.
EXPOSURE_MIN = 40
STATIC_SOURCES = ("areas", "seoul_boundary", "stores", "resident", "worker")
COUNT_FIELDS = (
    "SIMILR_INDUTY_STOR_CO",
    "STOR_CO",
    "FRC_STOR_CO",
    "OPBIZ_STOR_CO",
    "CLSBIZ_STOR_CO",
)
BASELINE_FIELDS = (
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
METHODS = ["service", "strict", "s_only", "no_s", "past_close", "popular"]
METHOD_NAMES = {
    "service": "현재 코드 90점(점포·상주·직장은 2026Q2 근사)",
    "strict": "현재 코드 90점(기준 시점 이후 자료 미사용)",
    "s_only": "생존 문항 S1~S4만",
    "no_s": "수요·경쟁 문항 D·C만",
    "past_close": "과거 폐업률이 서울 대비 낮은 순",
    "popular": "상권에 점포가 많은 순",
}


def split_versions(versions: list[dict], cutoff: str = CUTOFF) -> tuple[list[dict], list[dict]]:
    """기준 시점 입력 버전과 이후 성과용 개폐업 버전을 나눕니다. 겹치는 분기는 없습니다."""
    for source in STATIC_SOURCES:
        if sum(v["source"] == source for v in versions) != 1:
            raise ValueError(f"{source} 원천은 한 버전만 있어야 합니다.")
    lifecycle = sorted(v["quarter"] for v in versions if v["source"] == "lifecycle")
    past = get_recent_quarters(base_quarter=cutoff, count=PAST_N)
    later = [q for q in lifecycle if q > cutoff][:FUTURE_N]
    if len(later) != FUTURE_N or later != get_recent_quarters(
        base_quarter=later[-1], count=FUTURE_N
    ):
        raise ValueError("기준 시점 이후 연속된 4개 분기 개폐업 자료가 필요합니다.")
    if not set(past) <= set(lifecycle):
        raise ValueError("기준 시점까지 연속된 8개 분기 개폐업 자료가 필요합니다.")
    floating = [v for v in versions if v["source"] == "floating" and v["quarter"] == cutoff]
    if len(floating) != 1:
        raise ValueError("기준 분기 유동인구 자료가 하나 필요합니다.")
    asof = [
        v
        for v in versions
        if v["source"] in STATIC_SOURCES or (v["source"] == "lifecycle" and v["quarter"] in past)
    ] + floating
    future = [v for v in versions if v["source"] == "lifecycle" and v["quarter"] in later]
    return asof, future


def iter_lifecycle(adapter: LocalAdapter, version: dict):
    """한 분기 전체 상권 행을 한 줄씩 읽어 메모리 사용을 줄입니다."""
    with adapter.connection() as db:
        fields = db.execute(
            "SELECT columns_json FROM source_fields WHERE version_id=?", (version["version_id"],)
        ).fetchone()
        columns = json.loads(fields[0])
        for (payload,) in db.execute(
            "SELECT payload FROM lifecycle WHERE version_id=?", (version["version_id"],)
        ):
            yield dict(zip(columns, json.loads(payload), strict=True))


def pool_rows(rows) -> list[dict]:
    """상권 행을 분기·서울 업종별로 더해 서울 합산 행을 만듭니다. 비율은 건수로 다시 셉니다."""
    sums: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: dict.fromkeys(COUNT_FIELDS, 0.0)
    )
    for row in rows:
        target = sums[(str(row["STDR_YYQU_CD"]), str(row["SVC_INDUTY_CD"]))]
        for field in COUNT_FIELDS:
            value = row.get(field)
            if value is None:
                raise ValueError("서울 합산에 쓸 건수가 비어 있습니다.")
            target[field] += float(value)
    return [
        normalize_row({"STDR_YYQU_CD": q, "TRDAR_CD": "11", "SVC_INDUTY_CD": s, **counts})
        for (q, s), counts in sums.items()
    ]


def seoul_baseline(pooled: list[dict], base: str, count: int) -> dict:
    """measure_lifecycle_baseline.py와 같은 집계·필드로 기준선을 만듭니다."""
    frame = aggregate_rows(pooled, "11", base, count)
    result = {}
    for row in frame.to_dict("records"):
        code = row["service_id"]
        if code in INDUSTRIES_WITHOUT_SEOUL:
            continue
        values = {key: row[key] for key in BASELINE_FIELDS}
        values["exposure"] = row["avg_store_count"] * count
        result[code] = {
            k: None if isinstance(v, float) and not math.isfinite(v) else v
            for k, v in values.items()
        }
    return result


def period_counts(rows: list[dict], area: str, base: str) -> dict[str, dict[str, int]]:
    """서비스 집계 결과의 분기별 건수를 그대로 더합니다. 한 분기라도 비면 그 업종은 뺍니다."""
    if not rows:
        return {}
    frame = aggregate_rows(rows, area, base, FUTURE_N)
    out = {}
    for detail in frame.attrs["quarterly_detail"]["industries"]:
        series = [detail["store_counts"], detail["opened_counts"], detail["closed_counts"]]
        if any(v is None for values in series for v in values):
            continue
        exposure, opened, closed = (sum(values) for values in series)
        out[detail["industry_id"]] = {"exposure": exposure, "opened": opened, "closed": closed}
    return out


def area_outcomes(rows: list[dict], area: str, base: str, seoul_future: dict) -> dict:
    """이후 4분기 성과입니다. 노출량이 적거나 서울 같은 업종 폐업이 없으면 재지 않습니다."""
    out = {}
    for code, counts in period_counts([normalize_row(r) for r in rows], area, base).items():
        seoul = seoul_future.get(code)
        if counts["exposure"] < EXPOSURE_MIN or not seoul or seoul["closed"] <= 0:
            continue
        rate = seoul["closed"] / seoul["exposure"]
        out[code] = {**counts, "expected": counts["exposure"] * rate}
    return out


def to_wgs84(x: float, y: float) -> tuple[float, float]:
    """app.geo에는 정방향 변환만 있어 반복 계산으로 되돌립니다. 0.5m 안에 들지 않으면 거절합니다."""
    lat, lon = 37.55, 126.99
    for _ in range(50):
        fx, fy = to_epsg5181(lat, lon)
        if abs(x - fx) < 0.01 and abs(y - fy) < 0.01:
            return lat, lon
        lat += (y - fy) / 110940
        lon += (x - fx) / (111320 * math.cos(math.radians(lat)))
    fx, fy = to_epsg5181(lat, lon)
    if math.hypot(x - fx, y - fy) > 0.5:
        raise ValueError("상권 대표 좌표를 위경도로 바꾸지 못했습니다.")
    return lat, lon


class CachedAdapter(LocalAdapter):
    """조건 없는 전체 조회(상권 경계·상주·직장)는 상권마다 같으므로 한 번만 읽습니다."""

    def __init__(self, path, versions):
        super().__init__(path, versions)
        self._cache: dict[str, list[dict]] = {}

    def rows(self, source, *, area_codes=None, bounds=None):
        if area_codes is not None or bounds is not None:
            return super().rows(source, area_codes=area_codes, bounds=bounds)
        if source not in self._cache:
            self._cache[source] = super().rows(source)
        return self._cache[source]


def score_rows(data: dict) -> list[dict]:
    sample = {
        **data,
        "education_zones": {"status": "not_queried", "zones": []},
        "facilities": {"data": {"queries": {}, "places": {}}},
    }
    return scoring.evaluate(sample)["rows"]


def strict_data(data: dict) -> dict:
    """기준 시점 이후 원천(점포·상주·직장)을 빼고 서비스의 기존 미확인·대체 경로로 채점합니다."""
    fp = data["floating_population"]
    return {
        **data,
        "commercial_collection_complete": False,
        "floating_population": {**fp, "resident": None, "worker": None},
    }


def points(row: dict, prefixes: tuple[str, ...]) -> float:
    return sum(v["points"] or 0 for k, v in row["items"].items() if k.startswith(prefixes))


def orders(rows: list[dict], strict_rows: list[dict], data: dict) -> dict[str, list[str]]:
    """같은 후보 집합(규제 금지·공간 제외를 뺀 업종)에서 방식별 추천 순서를 만듭니다."""

    def allowed(items):
        return [
            r
            for r in items
            if r["regulation"] != "금지" and not r.get("space", {}).get("excluded", False)
        ]

    candidates = allowed(rows)
    stores = {
        r["industry_id"]: r["metrics"].get("avg_store_count")
        for r in data.get("business_lifecycle", {}).get("industries", [])
    }

    def tie(r):
        return (-(r["coverage"] or 0), r["code"])

    def past_close(r):
        s1 = r["items"]["S1"]
        observed = s1["status"] == "observed"
        return (not observed, s1["value"] if observed else 0, r["code"])

    return {
        "service": [r["code"] for r in sorted(candidates, key=scoring.rank_key)],
        "strict": [r["code"] for r in sorted(allowed(strict_rows), key=scoring.rank_key)],
        "s_only": [
            r["code"] for r in sorted(candidates, key=lambda r: (-points(r, ("S",)), *tie(r)))
        ],
        "no_s": [
            r["code"] for r in sorted(candidates, key=lambda r: (-points(r, ("D", "C")), *tie(r)))
        ],
        "past_close": [r["code"] for r in sorted(candidates, key=past_close)],
        "popular": [
            r["code"]
            for r in sorted(candidates, key=lambda r: (-(stores.get(r["code"]) or 0), r["code"]))
        ],
    }


def compact(rows: list[dict]) -> dict:
    return {
        r["code"]: {
            "lower": r["lower"],
            "coverage": r["coverage"],
            "badge": r["badge"],
            "items": {k: [v["status"], v["points"]] for k, v in r["items"].items() if k != "L"},
        }
        for r in rows
    }


_WORKER: dict = {}


def init_worker(path: str, versions: list[dict], baseline: dict, cutoff: str) -> None:
    """작업 프로세스마다 네트워크 차단과 기준 시점 상수 대체를 프로세스 수명 동안 유지합니다."""
    stack = ExitStack()
    stack.enter_context(block_network())
    stack.enter_context(patch.object(scoring, "BASELINE_BASE_QUARTER", cutoff))
    stack.enter_context(patch.object(scoring, "BASELINE_QUARTER_COUNT", PAST_N))
    stack.enter_context(patch.object(scoring, "SEOUL_INDUSTRY_LIFECYCLE_BASELINE", baseline))
    _WORKER.update(stack=stack, adapter=CachedAdapter(Path(path), versions))


def score_area(area: dict) -> dict:
    code = str(area["TRDAR_CD"])
    lat, lon = to_wgs84(float(area["XCNTS_VALU"]), float(area["YDNTS_VALU"]))
    task = AnalysisTask(
        request_id="forward-" + code,
        site=Site(input_address=code, road_address=code, latitude=lat, longitude=lon),
        radius_m=500,
    )
    data = _WORKER["adapter"].analyze(task)
    selected = data["area_selection"].get("area_code")
    if selected != code:
        return {"area": code, "skipped": "대표 좌표가 다른 상권으로 선택됨", "selected": selected}
    rows = score_rows(data)
    strict_rows = score_rows(strict_data(data))
    return {
        "area": code,
        "district": str(area["SIGNGU_CD"]),
        "area_type": area.get("TRDAR_SE_C"),
        "site": [lat, lon],
        "orders": orders(rows, strict_rows, data),
        "badges": {r["code"]: r["badge"] for r in rows},
        "scores": compact(rows),
    }


def load_future(adapter: LocalAdapter, versions: list[dict]):
    by_area: dict[str, list[dict]] = defaultdict(list)
    seoul = []
    for version in versions:
        for row in iter_lifecycle(adapter, version):
            by_area[str(row["TRDAR_CD"])].append(
                {k: row[k] for k in ("STDR_YYQU_CD", "TRDAR_CD", "SVC_INDUTY_CD", *COUNT_FIELDS)}
            )
            seoul.append(row)
    return by_area, pool_rows(seoul)


def baseline_check(adapter: LocalAdapter, versions: list[dict]) -> dict:
    """같은 상권 합산 방식으로 운영 12분기 기준선을 재현하는지 점검합니다."""
    quarters = sorted(v["quarter"] for v in versions if v["source"] == "lifecycle")[-12:]
    selected = [v for v in versions if v["source"] == "lifecycle" and v["quarter"] in quarters]
    pooled = pool_rows(row for v in selected for row in iter_lifecycle(adapter, v))
    rebuilt = seoul_baseline(pooled, quarters[-1], 12)
    ratios: dict[str, list[float]] = defaultdict(list)
    for code, official in SEOUL_INDUSTRY_LIFECYCLE_BASELINE.items():
        for key in ("recent_year_close_rate", "turnover_rate", "oldest_year_close_rate"):
            a, b = official.get(key), (rebuilt.get(code) or {}).get(key)
            if scoring.valid(a) and scoring.valid(b) and a > 0:
                ratios[key].append(b / a)
    return {
        key: {"n": len(v), "mean_ratio": sum(v) / len(v), "min": min(v), "max": max(v)}
        for key, v in ratios.items()
    }


def run(data_path: Path, out: Path, *, cutoff=CUTOFF, workers=4, limit=None, seed=20261026):
    if out.exists():
        raise ValueError("결과 폴더가 이미 있습니다. 새 경로를 지정하세요.")
    started = time.time()
    with block_network():
        full = LocalAdapter(data_path)
        asof, future = split_versions(full.versions, cutoff)
        past = [v for v in asof if v["source"] == "lifecycle"]
        baseline = seoul_baseline(
            pool_rows(row for v in past for row in iter_lifecycle(full, v)), cutoff, PAST_N
        )
        future_rows, future_pooled = load_future(full, future)
        last = max(v["quarter"] for v in future)
        seoul_future = period_counts(future_pooled, "11", last)
        outcomes = {
            a: area_outcomes(rows, a, last, seoul_future) for a, rows in future_rows.items()
        }
        check = baseline_check(full, full.versions)
        areas = sorted(
            CachedAdapter(data_path, asof).rows("areas"), key=lambda r: str(r["TRDAR_CD"])
        )
    if limit:
        areas = sorted(random.Random(seed).sample(areas, limit), key=lambda r: str(r["TRDAR_CD"]))
    out.mkdir(parents=True)
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=init_worker,
        initargs=(str(data_path), asof, baseline, cutoff),
    ) as pool:
        scored = list(pool.map(score_area, areas, chunksize=8))
    records, skipped = [], []
    for item in scored:
        if "skipped" in item:
            skipped.append(item)
            continue
        item["outcomes"] = outcomes.get(item["area"], {})
        records.append(item)
    with (out / "records.jsonl").open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    metrics = forward_metrics.evaluate(records, METHODS, seed=seed)
    backend = Path(__file__).resolve().parents[1]
    manifest = {
        "kind": "forward-time-split-code-score-validation",
        "llm_calls": 0,
        "external_api_calls": 0,
        "network": "소켓 연결·DNS·UDP 전송 차단",
        "cutoff": cutoff,
        "past_lifecycle_quarters": sorted(v["quarter"] for v in past),
        "future_quarters": sorted(v["quarter"] for v in future),
        "input_versions": asof,
        "outcome_versions": future,
        "exposure_min": EXPOSURE_MIN,
        "methods": METHOD_NAMES,
        "area_n": len(areas),
        "scored_area_n": len(records),
        "skipped": skipped,
        "areas_with_outcomes": sum(bool(r["outcomes"]) for r in records),
        "baseline_reproduction": check,
        "seconds": round(time.time() - started, 1),
        "seed": seed,
        "source_hashes": {
            str(p.relative_to(backend)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                backend / "app/agentic/scoring.py",
                backend / "app/agentic/inputs.py",
                Path(__file__),
                Path(forward_metrics.__file__),
            )
        },
        "outcome_rows_used_in_features": 0,
    }
    (out / "results.json").write_text(
        json.dumps({"manifest": manifest, "metrics": metrics}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "report.md").write_text(report(manifest, metrics), encoding="utf-8")
    return manifest, metrics


def fmt(value, digits=3):
    return "—" if value is None else f"{value:.{digits}f}"


def ci(bounds, digits=3) -> str:
    return "—" if not bounds else f"{bounds[0]:.{digits}f} ~ {bounds[1]:.{digits}f}"


def report(manifest: dict, metrics: dict) -> str:
    past = manifest["past_lifecycle_quarters"]
    lines = [
        "# 시점 분리 전진 검증 결과",
        "",
        f"- 기준 시점 {manifest['cutoff']}: 개폐업 {past[0]}~{past[-1]} 8분기로 채점",
        f"- 성과: {manifest['future_quarters'][0]}~{manifest['future_quarters'][-1]} "
        "같은 상권·업종의 실제 폐업·개업",
        f"- 상권 {manifest['scored_area_n']}/{manifest['area_n']}곳 채점, "
        f"제외 {len(manifest['skipped'])}곳 · LLM·외부 API 호출 0회",
        "- 표준화 폐업비 = 실제 폐업 합 / (노출량 × 같은 기간 서울 같은 업종 폐업률) 합. "
        "1보다 작으면 서울보다 덜 닫음",
        "",
        "## 추천 5개와 나머지 후보",
        "",
        "| 방식 | 추천 5개 폐업비 | 나머지 폐업비 | 비율(추천/나머지) | 95% 구간 "
        "| 순증률 차이(%p) | 95% 구간 | 추천이 낮은 상권 비율 |",
        "| --- | ---: | ---: | ---: | --- | ---: | --- | ---: |",
    ]
    for method in METHODS:
        m = metrics["methods"][method]
        t = m["top_vs_rest"]
        lines.append(
            f"| {METHOD_NAMES[method]} | {fmt(t['top5']['scr'])} | {fmt(t['rest']['scr'])} | "
            f"{fmt(t['scr_ratio_top5_over_rest'])} | {ci(t['scr_ratio_ci95'])} | "
            f"{fmt(t['net_change_gap'], 2)} | {ci(t['net_change_gap_ci95'], 2)} | "
            f"{fmt(m['area_wins']['top5_lower_share'], 2)} "
            f"({m['area_wins']['compared_areas']}곳) |"
        )
    lines += [
        "",
        "## 현재 코드 90점 대비 다른 방식의 추천 5개 폐업비 (다른 방식 / 현재)",
        "",
        "| 방식 | 비율 | 95% 구간 |",
        "| --- | ---: | --- |",
    ]
    for method, stats in metrics["paired_vs_reference"].items():
        lines.append(
            f"| {METHOD_NAMES[method]} | {fmt(stats['scr_ratio'])} | {ci(stats['ci95'])} |"
        )
    lines += [
        "",
        "## 현재 코드 90점 추천 순위 구간별 이후 성과",
        "",
        "| 순위 | 상권·업종 수 | 표준화 폐업비 | 폐업률(%) | 순증률(%) | 실제 폐업 | 기대 폐업 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for band in metrics["methods"]["service"]["rank_bands"]:
        lines.append(
            f"| {band['ranks']} | {band['pairs']} | {fmt(band['scr'])} | "
            f"{fmt(band['close_rate'], 2)} | {fmt(band['net_change_rate'], 2)} | "
            f"{band['closed']:.0f} | {band['expected']:.1f} |"
        )
    lines += ["", "## 배지별 이후 성과(현재 코드 90점)", ""]
    for badge, s in metrics["badges"].items():
        lines.append(
            f"- {badge}: {s['pairs']}건 · 표준화 폐업비 {fmt(s['scr'])} · "
            f"순증률 {fmt(s['net_change_rate'], 2)}%"
        )
    lines += ["", "## 추천 5개 측정 가능 비율·편중", ""]
    for method in METHODS:
        m = metrics["methods"][method]
        c = m["concentration"]
        lines.append(
            f"- {METHOD_NAMES[method]}: 측정 가능 {fmt(m['top5_measured_share'], 2)} · "
            f"등장 업종 {c['distinct_industries']}개 · 상위 10업종 점유 {fmt(c['top10_share'], 2)}"
        )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="LLM·외부 API 없이 코드 90점의 시점 분리 검증을 합니다."
    )
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cutoff", default=CUTOFF)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    manifest, _ = run(
        args.data, args.out, cutoff=args.cutoff, workers=args.workers, limit=args.limit
    )
    print(json.dumps({k: manifest[k] for k in ("scored_area_n", "areas_with_outcomes", "seconds")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
