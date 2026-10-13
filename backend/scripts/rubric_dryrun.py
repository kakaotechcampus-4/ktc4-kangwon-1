"""v0.8 시험 채점. 운영 모듈·LLM 없이 저장된 표본만 읽는다."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from bisect import bisect_right
from collections import Counter
from functools import cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.business_lifecycle.baseline import (  # noqa: E402
    BASELINE_BASE_QUARTER,
    BASELINE_QUARTER_COUNT,
    SEOUL_INDUSTRY_LIFECYCLE_BASELINE,
)
from app.agents.commercial_area.baseline import SEOUL_INDUSTRY_DENSITY_PERCENTILES  # noqa: E402
from app.agents.floating_population import baseline as population_baseline  # noqa: E402
from app.agents.floating_population.models import quarter_days  # noqa: E402
from app.agents.floating_population.population import (  # noqa: E402
    RESIDENT_KIND,
    WORKER_KIND,
    _age_share,
    load_snapshot,
)
from app.industries import DATA_DIR  # noqa: E402
from app.industries.catalog import INDUSTRIES  # noqa: E402

WEIGHTS = {
    "D1": 10,
    "D2": 10,
    "D3": 10,
    "D4": 5,
    "C1": 15,
    "C4": 10,
    "S1": 7.5,
    "S2": 7.5,
    "S3": 7.5,
    "S4": 7.5,
    "L": 10,
}
AMBIGUITIES: list[str] = []


def valid(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def result(
    item: str, grade: int | None = None, *, status="unknown", reason="자료 부족", value=None
):
    return {
        "status": "observed" if grade is not None else status,
        "grade": grade,
        "points": WEIGHTS[item] * grade / 4 if grade is not None else None,
        "value": value,
        "reason": reason,
    }


@cache
def seoul_age_share(kind: str, quarter: str) -> dict:
    records = [r for r in load_snapshot(kind) if r.stdr_yyqu_cd == quarter]
    return _age_share(records) if records else {}


def score_item(
    item: str, profile: dict, code: str, data: dict, exposure_min: float = 40, c1_alpha: float = 0.5
):
    if item == "L":
        return result(
            item, reason="시험에서는 decision 도구·새 fact_id 근거·판단 채점을 실행하지 않음"
        )
    fp = data.get("floating_population", {})
    bench = fp.get("benchmark", {})
    pop = fp.get("population", {})

    def unknown(reason):
        return result(item, reason=reason)

    def na():
        return result(item, status="n.a.", reason="사용자 승인 미적용")

    def forward(v):
        return bisect_right([0.80, 0.95, 1.05, 1.20], v)

    def reverse(v):
        return 4 - forward(v)

    if item == "D1":
        pattern = profile.get("pattern")
        if pattern == "무관":
            return na()
        if pattern == "종일형":
            value = bench.get("mean_daily_per_trade_area")
            if not valid(value) or value < 0:
                return unknown("전체 일평균 부족")
            p = population_baseline.daily_total_percentile(value)
            return result(
                item, bisect_right([20, 40, 60, 80], p), reason="종일형 규모만", value=value
            )
        bands = profile.get("primary_bands", "").split(";")
        count = fp.get("reliability", {}).get("covered_trade_areas")
        quarter = fp.get("period_code")
        raw = pop.get("by_time") or {}
        shares = pop.get("time_per_hour_share", {})
        if (
            not quarter
            or not valid(count)
            or count <= 0
            or not all(valid(raw.get(b)) and valid(shares.get(b)) for b in bands)
        ):
            return unknown("시간대 원값·관측 상권 집합 부족")
        if any("결측 수치" in w for w in data.get("floating_warnings", [])):
            return unknown("유효 시간대 관측 상권 집합 검증 불가")
        daily = sum(raw[b] for b in bands) / count / quarter_days(quarter)
        base = sum(population_baseline.TIME_PER_HOUR_SHARE_AVG[b] for b in bands)
        ratio = sum(shares[b] for b in bands) / base
        if len(bands) == 1:
            p = population_baseline.time_band_percentile(bands[0], daily)
        elif pattern in population_baseline.PATTERN_DAILY_PERCENTILES:
            p = population_baseline.pattern_percentile(pattern, daily)
        else:
            return unknown("패턴 합계 기준선 없음")
        grade = min(forward(ratio), bisect_right([20, 40, 60, 80], p))
        return result(item, grade, reason="적합성·규모 최소 등급", value={"r": ratio, "p": p})
    if item == "D2":
        day = profile.get("day_pattern")
        if day == "무관":
            return na()
        r = bench.get("weekend_index")
        if not valid(r) or r <= 0:
            return unknown("요일 지수 부족")
        if day not in {"평일형", "주말형"}:
            return unknown("요일 프로필 없음")
        value = 1 / r if day == "평일형" else r
        return result(item, forward(value), value=value, reason="요일 프로필 지수")
    if item == "D3":
        kind = profile.get("target_population")
        if not kind or kind == "—":
            return na()
        ages = [age for age in profile.get("target_age_bands", "").split(";") if age]
        if not ages:
            return unknown("대상 연령 프로필 공란")
        replaced = False
        if kind == "유동":
            local = pop.get("age_share", {})
            baseline = population_baseline.AGE_SHARE_AVG
        else:
            block = fp.get({"상주": "resident", "직장": "worker"}.get(kind, ""), {}) or {}
            local = block.get("age_share", {})
            snapshot_kind = RESIDENT_KIND if kind == "상주" else WORKER_KIND
            baseline = seoul_age_share(snapshot_kind, block.get("period_code", ""))
            if not all(valid(local.get(age)) and valid(baseline.get(age)) for age in ages):
                local = pop.get("age_share", {})
                baseline = population_baseline.AGE_SHARE_AVG
                replaced = True
        if not all(valid(local.get(age)) and valid(baseline.get(age)) for age in ages):
            return unknown("연령 비중·서울 분모 부족")
        denominator = sum(baseline[age] for age in ages)
        if denominator <= 0:
            return unknown("서울 대상 연령 비중 합이 0")
        ratio = sum(local[age] for age in ages) / denominator
        return result(
            item,
            forward(ratio),
            value={
                "r": ratio,
                "population": "유동" if replaced else kind,
                "requested_population": kind,
            },
            reason="유동 연령 대체" if replaced else "동일 모집단 대상 연령 비중 합/서울 비중 합",
        )
    if item == "D4":
        value = fp.get("trend", {}).get("yoy_change")
        if not valid(value):
            return unknown("동일 상권 전년 동기 없음")
        return result(
            item,
            bisect_right([-10, -3, 3, 10], 100 * value),
            value=value,
            reason="전년 동기 변화율",
        )
    if item == "C1":
        ca = data.get("commercial_area", {})
        if ca.get("radius_m") != 500:
            return unknown("500m 기준선 범위 불일치")
        if not data.get("commercial_collection_complete", False) or code in data.get(
            "commercial_split_missing", []
        ):
            return unknown("반경 점포·소분류 집계 불완전")
        row = next((r for r in ca.get("by_middle", []) if r.get("code") == code), None)
        if row is None:
            return unknown("업종 행 없음; 원문 없이 점포 0으로 추정하지 않음")
        median = SEOUL_INDUSTRY_DENSITY_PERCENTILES[code][50]
        density = row.get("density_per_km2")
        if median < 0.01 or not valid(density):
            return unknown("희소 기준선·밀도 결측")
        q = density / median
        if c1_alpha:
            daily = bench.get("mean_daily_per_trade_area")
            if not valid(daily) or daily <= 0:
                return unknown("유동 규모 결측·0")
            q /= (daily / population_baseline.DAILY_TOTAL_PERCENTILES[50]) ** c1_alpha
        return result(
            item,
            4 - bisect_right([0.5, 0.8, 1.2, 1.5], q),
            value=q,
            reason=f"C1 α={c1_alpha}; 현재 API/2026Q2 밀도 기준선 시점 차이 있음",
        )
    if item == "C4":
        facilities = profile.get("required_facilities", "")
        if not facilities:
            return na()
        maximum = float(profile["max_distance_m"])
        obs = data.get("facilities", {}).get("data", {})
        grades = []
        distances = {}
        for facility in facilities.split(";"):
            queries = [
                q
                for q in obs.get("queries", {}).values()
                if q.get("request", {}).get("facility_code") == facility and q.get("status") == "ok"
            ]
            ds = [
                obs.get("places", {}).get(pid, {}).get("distance_m")
                for q in queries
                for pid in q.get("place_ids", [])
                if obs.get("places", {}).get(pid, {}).get("category_code") == facility
            ]
            ds = [d for d in ds if valid(d) and d >= 0]
            if not ds:
                return unknown("시설 최근접 거리 미확인; 검색 0건을 부재로 확정하지 않음")
            distances[facility] = min(ds)
            t = min(ds) / maximum
            grades.append(4 - sum(t > edge for edge in [0.25, 0.5, 0.75, 1]))
        return result(item, min(grades), value=distances, reason="필수 시설별 최저 등급")
    bl = data.get("business_lifecycle", {})
    meta = bl.get("metadata", {})
    baseline = SEOUL_INDUSTRY_LIFECYCLE_BASELINE.get(code)
    row = next((r for r in bl.get("industries", []) if r.get("industry_id") == code), {})
    metrics = row.get("metrics", {})
    quarters = meta.get("quarter_count")
    if not baseline:
        return unknown("서울 대응 업종 없음")
    if not bl:
        return unknown("개폐업 자료 없음: " + "; ".join(data.get("business_warnings", [])))
    if meta.get("base_quarter") != BASELINE_BASE_QUARTER or quarters != BASELINE_QUARTER_COUNT:
        return unknown("개폐업 기준선 분석 기간 불일치")
    exposure = metrics.get("avg_store_count")
    if not row.get("data_complete") or not valid(exposure) or exposure * quarters < exposure_min:
        return unknown("개폐업 관측·전체 노출량 부족")
    if item in {"S2", "S4"}:
        details = data.get("lifecycle_quarterly", {})
        qs = details.get("quarters", [])
        detail = next(
            (r for r in details.get("industries", []) if r.get("industry_id") == code), {}
        )
        counts = detail.get("store_counts", [])
        if len(qs) < 8 or len(counts) != len(qs) or not all(valid(v) for v in counts):
            return unknown("기간별 노출량·비중첩 비교창 검증 불가")
        if min(sum(counts[:4]), sum(counts[-4:])) < exposure_min:
            return unknown("과거·최근 각각 노출량 부족")
    if item in {"S1", "S3"}:
        key = "recent_year_close_rate" if item == "S1" else "turnover_rate"
        local = metrics.get(key)
        base = baseline[key]
        if not valid(local) or not valid(base) or base <= 0:
            return unknown("비율 분모 부족")
        r = local / base
        grade = reverse(r)
    elif item == "S2":
        local = metrics.get("net_change_rate")
        turn = baseline["turnover_rate"]
        if not valid(local) or not valid(turn) or turn <= 0:
            return unknown("서울 회전율 분모 부족")
        r = 1 + (local - baseline["net_change_rate"]) / turn
        grade = forward(r)
    else:
        recent = metrics.get("recent_year_close_rate")
        past = metrics.get("oldest_year_close_rate")
        base_recent = baseline["recent_year_close_rate"]
        base_past = baseline["oldest_year_close_rate"]
        if (
            not all(valid(v) for v in [recent, past, base_recent, base_past])
            or min(past, base_past, base_recent) <= 0
        ):
            return unknown("상권 과거 또는 서울 폐업률 분모 0·결측")
        r = (recent / past) / (base_recent / base_past)
        grade = reverse(r)
    return result(
        item,
        grade,
        value=r,
        reason="서울 동일 업종 대비; 누락 원천 0 보충=" + str(row.get("zero_filled_sources", 0)),
    )


def regulation(code: str, scan: dict) -> str:
    if scan.get("status") != "ok":
        return "unknown"
    zones = scan.get("zones", [])
    if not zones:
        return "해당 없음"
    if code not in {"I101", "I102", "R104", "I211"}:
        return "해당 없음"
    names = [str(z.get("name", "")) for z in zones]
    absolute = any("절대" in n for n in names)
    relative = any("상대" in n for n in names)
    if not absolute and not relative:
        return "unknown"
    if absolute and code in {"I101", "I102"}:
        return "금지"
    return "조건부"


def summarize(
    code: str,
    items: dict,
    g: str,
    *,
    coverage_min=0.75,
    lower_min=0.65,
    upper_max=0.45,
    domain_min=0.5,
):
    observed = sum(WEIGHTS[k] for k, v in items.items() if v["status"] == "observed")
    lower = sum(v["points"] for v in items.values() if v["points"] is not None)
    d = (
        sum(WEIGHTS[k] for k, v in items.items() if k.startswith("D") and v["status"] == "observed")
        / 35
    )
    c = (
        sum(WEIGHTS[k] for k, v in items.items() if k.startswith("C") and v["status"] == "observed")
        / 25
    )
    applicable = 100 - sum(WEIGHTS[k] for k, v in items.items() if v["status"] == "n.a.")
    d_applicable = 35 - sum(
        WEIGHTS[k] for k, v in items.items() if k.startswith("D") and v["status"] == "n.a."
    )
    c_applicable = 25 - sum(
        WEIGHTS[k] for k, v in items.items() if k.startswith("C") and v["status"] == "n.a."
    )
    coverage = observed / applicable if applicable else None
    upper = lower + applicable - observed
    lower_ratio = lower / applicable if applicable else None
    upper_ratio = upper / applicable if applicable else None
    d = d * 35 / d_applicable if d_applicable else None
    c = c * 25 / c_applicable if c_applicable else None
    qualifies = (
        coverage is not None
        and coverage >= coverage_min
        and (d is None or d >= domain_min)
        and (c is None or c >= domain_min)
        and lower_ratio is not None
        and lower_ratio >= lower_min
    )
    badge = (
        "비추천"
        if g == "금지"
        or (coverage is not None and coverage >= coverage_min and upper_ratio <= upper_max)
        else ("추천" if g == "해당 없음" else "조건부")
        if qualifies
        else "보류"
    )
    conditions = ["건축물 용도 등은 별도 확인 필요(현재 배지 차단 조건 아님)"]
    if applicable < 60:
        conditions.append("채점 가능한 문항이 적음")
    if not any(items.get(k, {}).get("status") == "observed" for k in ("D1", "D3")):
        conditions.append("손님 수요 근거 없음")
    if badge == "추천" and len(conditions) > 1:
        badge = "조건부"
    return {
        "code": code,
        "name": INDUSTRIES[code],
        "items": items,
        "lower": lower,
        "upper": upper,
        "lower_ratio": lower_ratio,
        "upper_ratio": upper_ratio,
        "coverage": coverage,
        "applicable_weight": applicable,
        "d_coverage": d,
        "c_coverage": c,
        "regulation": g,
        "badge": badge,
        "confirmation_conditions": conditions,
    }


def profiles() -> dict:
    with (DATA_DIR / "industry_profile.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if any(r["reviewed_v2"] != "true" for r in rows):
        raise ValueError("미승인 프로필")
    return {r["industry_code"]: r for r in rows}


def evaluate(sample: dict, *, exposure_min=40, c1_alpha=0.5, **thresholds) -> dict:
    rows = []
    for code, profile in profiles().items():
        items = {
            item: score_item(item, profile, code, sample, exposure_min, c1_alpha)
            for item in WEIGHTS
        }
        rows.append(
            summarize(
                code, items, regulation(code, sample.get("education_zones", {})), **thresholds
            )
        )
    top = sorted(
        [r for r in rows if r["regulation"] != "금지"],
        key=lambda r: (-r["lower"], -r["coverage"], r["code"]),
    )[:5]
    return {
        "address": sample["address"],
        "rows": rows,
        "top5": top,
        "top5_status": "v0.3 하한→coverage→코드 순 검토 후보",
        "badges": dict(Counter(r["badge"] for r in rows)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--samples", type=Path, default=Path(__file__).resolve().parents[1] / "cache/rubric_samples"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    args.samples = args.samples.resolve()
    if args.samples.is_relative_to(root) and not args.samples.is_relative_to(
        root / "backend/cache"
    ):
        parser.error("실데이터 출력은 저장소 밖 또는 backend/cache만 허용합니다.")
    samples = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(args.samples.glob("sample-*.json"))
    ]
    if not samples:
        raise SystemExit("표본 없음: 먼저 승인된 자료를 수집하세요.")
    reports = [evaluate(s) for s in samples]
    sensitivities = {}
    for parameter, base in [
        ("coverage_min", 0.75),
        ("lower_min", 0.65),
        ("upper_max", 0.45),
        ("domain_min", 0.5),
        ("exposure_min", 40),
    ]:
        sensitivities[parameter] = {
            str(round(base * factor, 3)): [
                evaluate(s, **{parameter: base * factor})["badges"] for s in samples
            ]
            for factor in [0.8, 0.9, 1, 1.1, 1.2]
        }
    unknown = {
        item: sum(
            r["items"][item]["status"] == "unknown" for report in reports for r in report["rows"]
        )
        / (len(reports) * 51)
        for item in WEIGHTS
    }
    out = {
        "reports": reports,
        "unknown_rates": unknown,
        "sensitivity": sensitivities,
        "unimplemented_rules": AMBIGUITIES,
        "lower_threshold_comparison": {
            str(threshold): [evaluate(s, lower_min=threshold)["badges"] for s in samples]
            for threshold in [0.60, 0.65, 0.70]
        },
    }
    (args.samples / "dryrun-results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "top5": [
                    {
                        "address": r["address"],
                        "candidates": [
                            (v["code"], v["badge"], v["lower"], v["upper"]) for v in r["top5"]
                        ],
                    }
                    for r in reports
                ],
                "badges": [r["badges"] for r in reports],
                "unknown_rates": unknown,
                "unimplemented_rules": AMBIGUITIES,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
