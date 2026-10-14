"""채점표 v0.8의 단일 순수 채점 엔진입니다. 파일 접근은 호출자가 to_thread로 격리합니다."""

from __future__ import annotations

import csv
import math
from bisect import bisect_right
from collections import Counter
from functools import cache
from typing import Any, TypeGuard

from app.agents.business_lifecycle.baseline import (
    BASELINE_BASE_QUARTER,
    BASELINE_QUARTER_COUNT,
    SEOUL_INDUSTRY_LIFECYCLE_BASELINE,
)
from app.agents.commercial_area.baseline import SEOUL_INDUSTRY_DENSITY_PERCENTILES
from app.agents.floating_population import baseline as population_baseline
from app.agents.floating_population.models import quarter_days
from app.agents.floating_population.population import (
    RESIDENT_KIND,
    WORKER_KIND,
    age_share,
    load_snapshot,
)
from app.industries import DATA_DIR
from app.industries.catalog import INDUSTRIES

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


def valid(value) -> TypeGuard[int | float]:
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
    return age_share(records) if records else {}


def score_item(
    item: str, profile: dict, code: str, data: dict, exposure_min: float = 40, c1_alpha: float = 0.5
):
    baseline: Any
    row: Any
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

    sources = {
        "D": "floating_population",
        "C1": "commercial_area",
        "C4": "map",
        "S": "business_lifecycle",
    }
    source = sources.get(item, sources.get(item[0]))
    # 승인 미적용은 결측으로 바꾸지 않습니다.
    na_item = (
        (item == "D1" and profile.get("pattern") == "무관")
        or (item == "D2" and profile.get("day_pattern") == "무관")
        or (item == "D3" and profile.get("target_population") in (None, "", "—"))
        or (item == "C4" and not profile.get("required_facilities"))
    )
    if (
        source in data.get("runtime_partial_sources", [])
        or (item == "C1" and "floating_population" in data.get("runtime_partial_sources", []))
    ) and not na_item:
        return unknown("원문 수집 부분 실패·행/페이지 누락")

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
            baseline = data.get("population_baselines", {}).get(snapshot_kind)
            if baseline is None:
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
        detail: dict[str, Any] = next(
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
    if scan.get("contains_verified") is False:
        return "unknown"
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
    d: float | None = (
        sum(WEIGHTS[k] for k, v in items.items() if k.startswith("D") and v["status"] == "observed")
        / 35
    )
    c: float | None = (
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
    d = d * 35 / d_applicable if d_applicable and d is not None else None
    c = c * 25 / c_applicable if c_applicable and c is not None else None
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


def rank_candidates(rows, limit=5):
    return sorted(
        [r for r in rows if r["regulation"] != "금지"],
        key=lambda r: (-r["lower"], -(r["coverage"] or 0), r["code"]),
    )[:limit]


def evaluate(
    sample: dict, *, exposure_min=40, c1_alpha=0.5, profile_rows=None, **thresholds
) -> dict:
    rows = []
    for code, profile in (profiles() if profile_rows is None else profile_rows).items():
        items = {
            item: score_item(item, profile, code, sample, exposure_min, c1_alpha)
            for item in WEIGHTS
        }
        rows.append(
            summarize(
                code, items, regulation(code, sample.get("education_zones", {})), **thresholds
            )
        )
    top = rank_candidates(rows)
    return {
        "address": sample["address"],
        "rows": rows,
        "top5": top,
        "top5_status": "v0.3 하한→coverage→코드 순 검토 후보",
        "badges": dict(Counter(r["badge"] for r in rows)),
    }
