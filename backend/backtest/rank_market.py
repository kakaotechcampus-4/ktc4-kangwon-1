"""저장된 지역 특화도 LQ를 관측 C1과 결합하는 민감도 비교입니다."""

from app.agentic.scoring import valid

MARKET_VARIANTS = {
    "lq_half": (0.5, "stored"),
    "lq_full": (1.0, "stored"),
    "lq_half_s_ratio": (0.5, "ratio"),
    "lq_full_s_ratio": (1.0, "ratio"),
}


def apply_market(row: dict, base: dict, data: dict, name: str) -> dict:
    if name not in MARKET_VARIANTS:
        return base
    item = row["items"]["C1"]
    # 희소 기준선·미확인 C1과 무관 업종의 정책고정 점수는 보완하지 않습니다.
    if item["status"] != "observed" or item.get("value") is None:
        return base
    commercial = next(
        (v for v in data["commercial_area"]["by_middle"] if v["code"] == row["code"]), None
    )
    if commercial is None or not valid(commercial.get("lq")) or commercial["lq"] < 0:
        raise ValueError("완전 집계된 관측 LQ가 필요합니다.")
    fraction, _ = MARKET_VARIANTS[name]
    lq = commercial["lq"]
    market_grade = 4 * lq / (1 + lq)
    grade = (1 - fraction) * base["item_grades"]["C1"] + fraction * market_grade
    points, grades = dict(base["item_points"]), dict(base["item_grades"])
    points["C1"], grades["C1"] = 15 * grade / 4, grade
    total = sum(v for v in points.values() if v is not None)
    return {
        **base,
        "points": total,
        "normalized": 80 * total / base["applicable"],
        "item_points": points,
        "item_grades": grades,
        "market": {"observed_lq": lq, "blend": fraction, "grade_from_lq": market_grade},
    }
