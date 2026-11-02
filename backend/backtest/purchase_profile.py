"""과거 추정 결제 분포와 같은 모집단 인구 구성의 적합도를 분리 계산합니다."""

import math
from bisect import bisect_right

from app.agents.floating_population.models import AGE_BANDS, DAYS
from app.industries.catalog import INDUSTRIES, INDUSTRY_TO_SEOUL
from backtest.rank_d_smooth import RATIO_EDGES, smooth_grade

SOURCE_QUARTER = "20242"
MINIMUM_TRANSACTIONS = 100
DAY_FIELDS = dict(zip(DAYS, ("MON", "TUES", "WED", "THUR", "FRI", "SAT", "SUN"), strict=True))
FIELDS = {
    "age": {a: f"AGRDE_{'60_ABOVE' if a == '60' else a}_SELNG_CO" for a in AGE_BANDS},
    "day": {d: f"{field}_SELNG_CO" for d, field in DAY_FIELDS.items()},
}
BLOCKS = {"유동": "population", "상주": "resident", "직장": "worker"}
BASELINES = {"상주": "REPOP", "직장": "WRC_POPLTN"}
MODES = {
    "control": {"D2": 0.0, "D3": 0.0},
    "D2_half": {"D2": 0.5, "D3": 0.0},
    "D3_half": {"D2": 0.0, "D3": 0.5},
    "both_quarter": {"D2": 0.25, "D3": 0.25},
    "both_half": {"D2": 0.5, "D3": 0.5},
}


def count(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if type(value) not in (str, int, float):
        raise ValueError("결제 건수는 결측 또는 음이 아닌 정수여야 합니다.")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0 or int(numeric) != numeric:
        raise ValueError("결제 건수는 결측 또는 음이 아닌 정수여야 합니다.")
    return int(numeric)


def build_profiles(rows):
    if not rows:
        raise ValueError("과거 서울 전체 추정매출 원문이 필요합니다.")
    lookup = {}
    for row in rows:
        code = row.get("SVC_INDUTY_CD")
        if (
            str(row.get("STDR_YYQU_CD")) != SOURCE_QUARTER
            or str(row.get("MEGA_CD")) != "11"
            or not code
            or code in lookup
        ):
            raise ValueError("2024Q2 서울 전체의 중복 없는 업종 원문이 필요합니다.")
        lookup[code] = row
    output = {}
    for code in INDUSTRIES:
        sources = INDUSTRY_TO_SEOUL.get(code, ())
        missing = sorted(set(sources) - lookup.keys())
        output[code] = {}
        for domain, fields in FIELDS.items():
            if not sources or missing:
                output[code][domain] = {
                    "available": False,
                    "reason": "missing_or_unsupported_industry_components",
                    "missing_source_codes": missing,
                }
                continue
            values = {k: [count(lookup[s].get(f)) for s in sources] for k, f in fields.items()}
            if any(v is None for group in values.values() for v in group):
                output[code][domain] = {"available": False, "reason": "missing_raw_count"}
                continue
            totals = {k: sum(v) for k, v in values.items()}
            total = sum(totals.values())
            if total < MINIMUM_TRANSACTIONS:
                output[code][domain] = {
                    "available": False,
                    "reason": "insufficient_published_transactions",
                    "total": total,
                }
                continue
            # 연령별 합계의 분모에 법인 등을 포함한 전체 결제 건수를 섞지 않습니다.
            output[code][domain] = {
                "available": True,
                "weights": {k: v / total for k, v in totals.items()},
                "published_counts": totals,
                "denominator": total,
                "source_codes": list(sources),
                "source_quarter": SOURCE_QUARTER,
                "represents_estimated_payments_not_distinct_customers": True,
            }
    return output


def affinity(local, baseline, weights):
    if set(local) != set(baseline) or set(local) != set(weights):
        raise ValueError("같은 구간의 결제 분포·관측 인구·기준선이 필요합니다.")
    if any(
        type(v) not in (int, float) or not math.isfinite(v) or v < 0
        for row in (local, baseline, weights)
        for v in row.values()
    ):
        raise ValueError("인구 비중과 결제 가중치는 음이 아닌 유한 수치여야 합니다.")
    if any(v <= 0 for v in baseline.values()) or any(
        not math.isclose(sum(row.values()), 1, abs_tol=0.002) for row in (local, baseline, weights)
    ):
        raise ValueError("관측 비중 합계와 양수 기준선 분모가 필요합니다.")
    ratio = sum(weights[k] * local[k] / baseline[k] for k in weights)
    fraction = (
        0.25 * bisect_right(RATIO_EDGES, ratio) + 0.75 * smooth_grade(ratio, RATIO_EDGES)
    ) / 4
    return {
        "available": True,
        "ratio": ratio,
        "fraction": fraction,
        "local_share": dict(local),
        "city_share": dict(baseline),
        "estimated_payment_weights": dict(weights),
        "represents_measured_customer_or_success_probability": False,
    }


def evidence_for(profile, data, items, purchase, city_day, floating_age):
    result = {
        "D2": {"available": False, "reason": "not_observed_or_complete_purchase_profile"},
        "D3": {"available": False, "reason": "not_observed_matching_population_or_profile"},
    }
    fp = data["floating_population"]
    if fp.get("period_code") != "20252":
        raise ValueError("고정된 2025Q2 평가 입력이 필요합니다.")
    if "floating_population" in data.get("runtime_partial_sources", []):
        return result
    if items["D2"]["status"] == "observed" and purchase["day"]["available"]:
        days = fp["population"].get("by_day", {})
        values = [days.get(d) for d in DAYS]
        if all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in values):
            total = sum(values)
            if total > 0:
                result["D2"] = affinity(
                    {d: days[d] / total for d in DAYS}, city_day, purchase["day"]["weights"]
                )
    kind = profile.get("target_population")
    item = items["D3"]
    if (
        item["status"] == "observed"
        and purchase["age"]["available"]
        and kind in BLOCKS
        and item.get("value", {}).get("population") == kind
        and item.get("value", {}).get("requested_population") == kind
    ):
        block = fp.get(BLOCKS[kind]) or {}
        local = block.get("age_share", {})
        baseline = (
            floating_age
            if kind == "유동"
            else data.get("population_baselines", {}).get(BASELINES[kind], {})
        )
        if (
            (kind == "유동" or block.get("period_code") == "20252")
            and all(type(local.get(a)) in (int, float) for a in AGE_BANDS)
            and all(type(baseline.get(a)) in (int, float) for a in AGE_BANDS)
        ):
            result["D3"] = {
                **affinity(
                    {a: local[a] for a in AGE_BANDS},
                    {a: baseline[a] for a in AGE_BANDS},
                    purchase["age"]["weights"],
                ),
                "source_population": kind,
                "payer_age_may_differ_from_service_user_age": True,
            }
    return result


def changed_fractions(original, statuses, evidence, mode):
    if mode not in MODES:
        raise ValueError("사전에 고정한 결제 분포 비교안이 필요합니다.")
    changed = dict(original)
    for name, blend in MODES[mode].items():
        if statuses[name] == "observed" and evidence[name]["available"]:
            changed[name] += blend * (evidence[name]["fraction"] - original[name])
    return changed
