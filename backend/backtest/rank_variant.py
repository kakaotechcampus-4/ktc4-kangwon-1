"""관측·미확인 상태와 배점을 보존하는 C1·S 비교용 순수 계산입니다."""

import math
from dataclasses import asdict, dataclass

from app.agentic.scoring import WEIGHTS, valid
from backtest.followup import C_ITEMS


@dataclass(frozen=True)
class Variant:
    name: str
    c1_strength: float = 1.0
    s_curve: str = "stored"


# 자료·라벨을 읽기 전에 정한 비교안입니다. 지원 범위나 미확인 불이익은 바꾸지 않습니다.
C1_VARIANTS = (
    Variant("current"),
    Variant("c1_half", c1_strength=0.5),
    Variant("c1_neutral", c1_strength=0.0),
)
S_CURVES = ("stored", "linear5", "linear2", "ratio")
ALL_VARIANTS = tuple(
    Variant(
        base.name if curve == "stored" else base.name + "_s_" + curve,
        c1_strength=base.c1_strength,
        s_curve=curve,
    )
    for base in C1_VARIANTS
    for curve in S_CURVES
)


def describe(variant: Variant) -> dict:
    return {
        **asdict(variant),
        "C1": "관측 등급을 2 + 강도 × (현재 등급 - 2)로 완화",
        "S": {
            "stored": "저장된 기존 S 연속식(기울기 10)",
            "linear5": "관측 S 등급의 기울기 5: 포화 경계를 넓힘",
            "linear2": "관측 S 등급의 기울기 2: 포화 경계를 더 넓힘",
            "ratio": "S1·S3·S4는 4/(1+r), S2는 2+2z/(1+|z|), z=r-1",
        }[variant.s_curve],
    }


def s_grade(name: str, ratio: float, curve: str) -> float:
    if name not in ("S1", "S2", "S3", "S4") or not valid(ratio):
        raise ValueError("S 문항·관측 비율이 올바르지 않습니다.")
    if name != "S2" and ratio < 0:
        raise ValueError("폐업·회전·추세 비율은 음수가 될 수 없습니다.")
    if curve == "ratio":
        if name == "S2":
            offset = ratio - 1
            return 2 + 2 * offset / (1 + abs(offset))
        return 4 / (1 + ratio)
    if curve not in {"linear5", "linear2"}:
        raise ValueError("저장 점수 외 S 비교 곡선이 아닙니다.")
    slope = 5 if curve == "linear5" else 2
    forward = max(0.0, min(4.0, 2 + slope * (ratio - 1)))
    return forward if name == "S2" else 4 - forward


def score_row(row: dict, variant: Variant) -> dict:
    if not 0 <= variant.c1_strength <= 1 or variant.s_curve not in S_CURVES:
        raise ValueError("C1 강도·S 곡선이 비교 범위 밖입니다.")
    applicable, total = 0.0, 0.0
    points, grades = {}, {}
    for name in C_ITEMS:
        item = row["items"][name]
        status = item["status"]
        if status not in {"observed", "unknown", "n.a."}:
            raise ValueError("알 수 없는 관측 상태입니다.")
        points[name], grades[name] = None, None
        if status != "n.a.":
            applicable += WEIGHTS[name]
        if status != "observed":
            if item["points"] is not None or item["grade"] is not None:
                raise ValueError("미확인·미적용 문항에는 점수가 없어야 합니다.")
            continue
        grade, point = item["grade"], item["points"]
        if (
            not valid(grade)
            or not valid(point)
            or not 0 <= grade <= 4
            or not math.isclose(point, WEIGHTS[name] * grade / 4, abs_tol=1e-10)
        ):
            raise ValueError("원본 관측 등급·점수·배점이 일치하지 않습니다.")
        if name == "C1" and variant.c1_strength != 1:
            grade = 2 + variant.c1_strength * (grade - 2)
            point = WEIGHTS[name] * grade / 4
        elif name.startswith("S") and variant.s_curve != "stored":
            grade = s_grade(name, item["value"], variant.s_curve)
            point = WEIGHTS[name] * grade / 4
        points[name], grades[name] = point, grade
        total += point
    if applicable <= 0:
        raise ValueError("적용 배점이 없습니다.")
    return {
        "normalized": 80 * total / applicable,
        "applicable": applicable,
        "points": total,
        "item_points": points,
        "item_grades": grades,
    }


def order_rows(rows: list[dict], values: dict, allowed: set[str] | None = None) -> list[str]:
    if len({r["code"] for r in rows}) != len(rows):
        raise ValueError("업종 코드가 중복됩니다.")
    candidates = [
        r
        for r in rows
        if r["regulation"] != "금지"
        and not r.get("space", {}).get("excluded", False)
        and (allowed is None or r["code"] in allowed)
    ]
    # 기준 실험의 환산·동점 기준을 그대로 사용합니다. 반올림으로 순위를 바꾸지 않습니다.
    return [
        r["code"]
        for r in sorted(
            candidates,
            key=lambda r: (
                -(values[r["code"]]["normalized"] + r.get("space", {}).get("adjustment", 0)),
                -(r["coverage"] or 0),
                r["code"],
            ),
        )
    ]
