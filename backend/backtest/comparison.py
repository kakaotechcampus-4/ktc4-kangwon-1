"""서비스 채점은 유지하고 코드 90점의 비교 방식을 오프라인에서 대조합니다."""

from app.agentic.scoring import WEIGHTS, adjusted_lower, rank_key, valid

CODE_ITEMS = tuple(name for name in WEIGHTS if name != "L")
CODE_WEIGHT = sum(WEIGHTS[name] for name in CODE_ITEMS)
METHODS = ("service", "applicable", "guarded")


def code_summary(row: dict) -> dict:
    items = row["items"]
    if items["L"]["status"] != "unknown" or items["L"]["points"] is not None:
        raise ValueError("코드 비교에는 L 판단 전 점수만 사용할 수 있습니다.")
    applicable = observed = points = 0.0
    unknown, not_applicable = [], []
    for name in CODE_ITEMS:
        item = items[name]
        status, value = item["status"], item["points"]
        if status == "observed":
            if not valid(value) or not 0 <= value <= WEIGHTS[name]:
                raise ValueError(f"관측 점수가 유효하지 않습니다: {name}")
            observed += WEIGHTS[name]
            points += value
        elif status in {"unknown", "n.a."}:
            if value is not None:
                raise ValueError(f"미확인·미적용 항목에 점수가 있습니다: {name}")
            (unknown if status == "unknown" else not_applicable).append(name)
        else:
            raise ValueError(f"알 수 없는 채점 상태입니다: {name}")
        if status != "n.a.":
            applicable += WEIGHTS[name]
    return {
        "code_points": points,
        "applicable_weight": applicable,
        "observed_weight": observed,
        "unknown_weight": applicable - observed,
        "coverage": observed / applicable if applicable else None,
        # unknown 배점은 분모에 남겨, 결측을 좋은 값으로 추정하지 않습니다.
        "normalized_lower": CODE_WEIGHT * points / applicable if applicable else None,
        "unknown_items": unknown,
        "not_applicable_items": not_applicable,
    }


def confidence_reasons(row: dict, summary: dict) -> list[str]:
    reasons = []
    # 서비스의 자료 충족도·최소 배점 조건을 참고한 실험 조건이며 운영 기준은 아닙니다.
    if summary["applicable_weight"] < 60:
        reasons.append("코드 적용 배점 60점 미만")
    if summary["coverage"] is None or summary["coverage"] < 0.75:
        reasons.append("코드 자료 충족도 75% 미만")
    if not any(row["items"][name]["status"] == "observed" for name in ("D1", "D3")):
        reasons.append("시간대·고객 연령 수요 근거 없음")
    for prefix in ("D", "C"):
        applicable = sum(
            WEIGHTS[name]
            for name in CODE_ITEMS
            if name.startswith(prefix) and row["items"][name]["status"] != "n.a."
        )
        observed = sum(
            WEIGHTS[name]
            for name in CODE_ITEMS
            if name.startswith(prefix) and row["items"][name]["status"] == "observed"
        )
        if applicable and observed / applicable < 0.5:
            reasons.append(f"{prefix} 자료 충족도 50% 미만")
    return reasons


def compare_rankings(rows: list[dict]) -> dict:
    codes = [row["code"] for row in rows]
    if len(set(codes)) != len(codes):
        raise ValueError("비교 업종이 중복됩니다.")
    summaries = {row["code"]: code_summary(row) for row in rows}
    reasons = {row["code"]: confidence_reasons(row, summaries[row["code"]]) for row in rows}
    allowed = [
        row
        for row in rows
        if row["regulation"] != "금지" and not row.get("space", {}).get("excluded", False)
    ]

    def normalized_key(row):
        summary = summaries[row["code"]]
        adjustment = row.get("space", {}).get("adjustment", 0)
        return (
            -(summary["normalized_lower"] + adjustment),
            # A/B에서는 점수 환산만 바꾸고 동점 해소 기준은 현행과 같게 둡니다.
            -(row["coverage"] or 0),
            row["code"],
        )

    comparable = [row for row in allowed if summaries[row["code"]]["normalized_lower"] is not None]
    ordered = {
        "service": sorted(allowed, key=rank_key),
        "applicable": sorted(comparable, key=normalized_key),
        "guarded": sorted(
            [row for row in comparable if not reasons[row["code"]]], key=normalized_key
        ),
    }
    ranks = {
        method: {row["code"]: rank for rank, row in enumerate(candidates, 1)}
        for method, candidates in ordered.items()
    }
    return {
        "top5": {
            method: [row["code"] for row in candidates[:5]]
            for method, candidates in ordered.items()
        },
        "rows": [
            {
                "code": row["code"],
                "name": row["name"],
                **summaries[row["code"]],
                "service_adjusted_lower": adjusted_lower(row),
                "guard_reasons": reasons[row["code"]],
                "ranks": {method: ranks[method].get(row["code"]) for method in METHODS},
                "regulation": row["regulation"],
                "space_excluded": row.get("space", {}).get("excluded", False),
            }
            for row in rows
        ],
    }
