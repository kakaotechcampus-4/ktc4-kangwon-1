"""미확인 점수의 비교용 추정치를 실제 관측 점수와 분리해 계산합니다."""

from app.agentic.availability import classify_item
from app.agentic.scoring import WEIGHTS
from backtest.comparison import code_summary
from backtest.followup import C_ITEMS

METHODS = {
    "lower_bound": "기존 하한 합산·미적용 보정",
    "observed_mean": "관측 항목 평균",
    "neutral_midpoint": "미확인 부분 중간값",
    "domain_shrink": "분야별 관측값의 중립 완화",
}
MODEL_WEIGHT = sum(WEIGHTS[name] for name in C_ITEMS)
PRIOR_WEIGHT = 10.0
MIN_COVERAGE = 0.75
MIN_DOMAIN_COVERAGE = 0.5
RANK_DECIMALS = 10


def estimate(row: dict) -> dict:
    code_summary(row)
    domains = {
        prefix: {
            "applicable": 0.0,
            "measured": 0.0,
            "measured_points": 0.0,
            "fixed": 0.0,
            "known_points": 0.0,
            "unknown": 0.0,
        }
        for prefix in ("D", "C", "S")
    }
    measured_items, unsupported = [], []
    for name in C_ITEMS:
        item = row["items"][name]
        state = classify_item(row["code"], name, item)
        if state == "not_applicable":
            continue
        domain = domains[name[0]]
        domain["applicable"] += WEIGHTS[name]
        if state == "profile_fixed":
            domain["fixed"] += WEIGHTS[name]
            domain["known_points"] += item["points"]
        elif state == "observed":
            domain["measured"] += WEIGHTS[name]
            domain["measured_points"] += item["points"]
            domain["known_points"] += item["points"]
            measured_items.append(name)
        else:
            domain["unknown"] += WEIGHTS[name]
            if state in {"unsupported_source", "sparse_baseline"}:
                unsupported.append(name)
    applicable = sum(d["applicable"] for d in domains.values())
    measured = sum(d["measured"] for d in domains.values())
    fixed = sum(d["fixed"] for d in domains.values())
    unknown = sum(d["unknown"] for d in domains.values())
    points = sum(d["known_points"] for d in domains.values())
    measured_points = sum(d["measured_points"] for d in domains.values())
    coverage = measured / (applicable - fixed) if applicable > fixed else None
    reasons = []
    if not measured:
        reasons.append("실제 관측 없음")
    if not any(name != "D4" for name in measured_items):
        reasons.append("업종을 구분할 수 있는 관측 근거 없음")
    if coverage is None or coverage < MIN_COVERAGE:
        reasons.append("실제 관측 자료 충족도 미달")
    domain_coverage = {}
    for prefix, domain in domains.items():
        expected = domain["applicable"] - domain["fixed"]
        fraction = domain["measured"] / expected if expected else None
        domain_coverage[prefix] = fraction
        if fraction is not None and fraction < MIN_DOMAIN_COVERAGE:
            reasons.append(f"{prefix} 분야의 실제 관측 자료 부족")
    if unsupported:
        reasons.append("원천 미지원·희소 기준선 항목 포함")
    scores = {method: None for method in METHODS}
    interval = None
    if applicable:
        lower = MODEL_WEIGHT * points / applicable
        upper = MODEL_WEIGHT * (points + unknown) / applicable
        interval = [lower, upper]
        scores["lower_bound"] = lower
        # 원본의 숫자·상태는 보존하고, 가정에 의한 값은 추정치로만 반환합니다.
        if measured:
            mean_fit = measured_points / measured
            values = {
                "lower_bound": points,
                "observed_mean": points + unknown * mean_fit,
                "neutral_midpoint": points + unknown * 0.5,
                "domain_shrink": sum(
                    d["known_points"]
                    + d["unknown"]
                    * ((d["measured_points"] + PRIOR_WEIGHT * 0.5) / (d["measured"] + PRIOR_WEIGHT))
                    for d in domains.values()
                ),
            }
            scores = {method: MODEL_WEIGHT * value / applicable for method, value in values.items()}
    return {
        "scores": scores,
        "interval": interval,
        "applicable_weight": applicable,
        "measured_weight": measured,
        "fixed_weight": fixed,
        "unknown_weight": unknown,
        "coverage": coverage,
        "domain_coverage": domain_coverage,
        "unsupported_items": unsupported,
        "sufficient_evidence": not reasons,
        "review_reasons": reasons,
    }


def rank(
    rows: list[dict], estimates: dict, method: str, *, sufficient_only=False, pending_only=False
) -> list[str]:
    if method not in METHODS or sufficient_only and pending_only:
        raise ValueError("비교 방식이나 후보 구분이 올바르지 않습니다.")
    allowed = [
        row
        for row in rows
        if row["regulation"] != "금지"
        and not row.get("space", {}).get("excluded", False)
        and estimates[row["code"]]["scores"][method] is not None
        and (not sufficient_only or estimates[row["code"]]["sufficient_evidence"])
        and (not pending_only or not estimates[row["code"]]["sufficient_evidence"])
    ]

    def point(row):
        value = estimates[row["code"]]["scores"][method] + row.get("space", {}).get("adjustment", 0)
        # 같은 추정식의 계산 순서에서 생기는 극미세 오차가 동점을 깨지 않게 합니다.
        return value if method == "lower_bound" else round(value, RANK_DECIMALS)

    return [
        row["code"]
        for row in sorted(
            allowed,
            key=lambda row: (
                -point(row),
                -(row["coverage"] or 0),
                row["code"],
            ),
        )
    ]
