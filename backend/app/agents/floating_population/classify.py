"""유동인구 유형 판정 — 결정론적 규칙.

같은 입력이면 항상 같은 결과가 나온다(LLM 없음). 임계치는 감이 아니라 서울 전체 상권 평균을
실측해(`baseline.py` 참고) 거기에 같은 폭을 더해 잡았다 — 근거는 아래 `SEOUL_AVG` 주석에 있다.

⚠️ 유형은 **추정**이다. 원본 데이터에 직업 컬럼이 없어서 "이 사람이 학생인지 직장인인지" 는 알 수
없고, 연령·시간대·요일 분포에서 유추할 뿐이다. 그래서 결과에 is_inference=True 를 붙인다.
"""

from __future__ import annotations

from pydantic import BaseModel

RULES_VERSION = "flpop-type-v1"

# 서울 전체 상권 평균 (2026Q2 · 1,648곳 · 13.2억 명 실측, 2026-09-09).
# 임계치를 "감" 이 아니라 이 평균 기준으로 잡기 위해 측정해 박아둔 값이다.
# 데이터가 분기 갱신되면 다시 재보고 필요하면 임계치와 RULES_VERSION 을 함께 올린다.
SEOUL_AVG = {
    "age_10": 0.128,
    "age_20": 0.180,
    "age_30_40": 0.344,
    "age_50_60": 0.348,
    "weekend_to_weekday": 0.973,
}

# 모든 유형에 같은 폭(서울 평균 +5%p)을 쓴다 — 어느 한 유형에 유리하게 맞추지 않기 위해.
MARGIN = 0.05

STUDENT_MIN = SEOUL_AVG["age_10"] + MARGIN  # 0.178
LEISURE_MIN = SEOUL_AVG["age_20"] + MARGIN  # 0.230
OFFICE_MIN = SEOUL_AVG["age_30_40"] + MARGIN  # 0.394
RESIDENT_MIN = SEOUL_AVG["age_50_60"] + MARGIN  # 0.398
# 직장인 상권은 주말에 비는 게 특징이다. 서울 평균(0.973) 보다 뚜렷하게 낮을 것을 요구한다.
OFFICE_WEEKEND_MAX = 0.90

MIXED = "혼합·불분명"


class TypeResult(BaseModel):
    label: str
    is_inference: bool = True
    reasons: list[str]
    # 판정에 쓴 숫자와 임계치를 함께 남긴다. 결정 에이전트가 한국어 문장이 아니라 값을
    # 인용해야 점수 계산과 근거 검증(Evidence.path)이 가능하다.
    signals: dict[str, float] = {}
    thresholds: dict[str, float] = {}
    rules_version: str = RULES_VERSION


def _pct(v: float) -> str:
    return f"{v:.0%}"


def classify(
    *,
    age_share: dict[str, float],
    weekend_to_weekday: float,
) -> TypeResult:
    """연령 비중과 주말/주중 비율로 유형을 판정한다.

    판정 순서가 곧 우선순위다 — 학생 → 직장인 → 여가상업 → 주거생활. 특징이 뾰족한 신호
    (10대·20대 편중)를 먼저 보고, 넓게 걸리는 신호(50·60대)를 마지막에 본다. 순서를 바꾸면
    학원가가 주거생활형으로 빨려 들어간다.
    """
    a10 = age_share["10"]
    a20 = age_share["20"]
    a3040 = age_share["30"] + age_share["40"]
    a5060 = age_share["50"] + age_share["60"]

    signals = {
        "age_10": round(a10, 4),
        "age_20": round(a20, 4),
        "age_30_40": round(a3040, 4),
        "age_50_60": round(a5060, 4),
        "weekend_to_weekday": round(weekend_to_weekday, 4),
    }
    thresholds = {
        "age_10_min": round(STUDENT_MIN, 4),
        "age_20_min": round(LEISURE_MIN, 4),
        "age_30_40_min": round(OFFICE_MIN, 4),
        "age_50_60_min": round(RESIDENT_MIN, 4),
        "office_weekend_max": OFFICE_WEEKEND_MAX,
    }

    if a10 >= STUDENT_MIN:
        return TypeResult(
            label="학생형",
            reasons=[
                f"10대 비중이 {_pct(a10)} 로 서울 평균 {_pct(SEOUL_AVG['age_10'])} 보다 높습니다"
                f" (기준 {_pct(STUDENT_MIN)} 이상)",
                "10대는 학교·학원 통행으로 보는 게 자연스럽습니다",
            ],
            signals=signals,
            thresholds=thresholds,
        )

    if a3040 >= OFFICE_MIN and weekend_to_weekday < OFFICE_WEEKEND_MAX:
        return TypeResult(
            label="직장인형",
            reasons=[
                f"30·40대 합이 {_pct(a3040)} 로 서울 평균"
                f" {_pct(SEOUL_AVG['age_30_40'])} 보다 높습니다"
                f" (기준 {_pct(OFFICE_MIN)} 이상)",
                f"주말 통행량이 주중의 {weekend_to_weekday:.2f} 배로 주중에 몰립니다"
                f" (기준 {OFFICE_WEEKEND_MAX} 미만,"
                f" 서울 평균 {SEOUL_AVG['weekend_to_weekday']:.2f})",
            ],
            signals=signals,
            thresholds=thresholds,
        )

    if a20 >= LEISURE_MIN:
        return TypeResult(
            label="여가상업형",
            reasons=[
                f"20대 비중이 {_pct(a20)} 로 서울 평균 {_pct(SEOUL_AVG['age_20'])} 보다 높습니다"
                f" (기준 {_pct(LEISURE_MIN)} 이상)",
                "20대는 대학생과 직장인을 데이터로 구분할 수 없어 학생 신호로는 쓰지 않았습니다",
            ],
            signals=signals,
            thresholds=thresholds,
        )

    if a5060 >= RESIDENT_MIN:
        return TypeResult(
            label="주거생활형",
            reasons=[
                f"50·60대 합이 {_pct(a5060)} 로 서울 평균"
                f" {_pct(SEOUL_AVG['age_50_60'])} 보다 높습니다"
                f" (기준 {_pct(RESIDENT_MIN)} 이상)",
                "생활권 통행이 많은 주거지 성격으로 보입니다",
            ],
            signals=signals,
            thresholds=thresholds,
        )

    return TypeResult(
        label=MIXED,
        signals=signals,
        thresholds=thresholds,
        reasons=[
            "어느 연령대도 서울 평균보다 뚜렷하게 높지 않아 특정 유형으로 단정하지 않았습니다",
            f"10대 {_pct(a10)} (기준 {_pct(STUDENT_MIN)})"
            f" · 30·40대 {_pct(a3040)} (기준 {_pct(OFFICE_MIN)})"
            f" · 20대 {_pct(a20)} (기준 {_pct(LEISURE_MIN)})"
            f" · 50·60대 {_pct(a5060)} (기준 {_pct(RESIDENT_MIN)})",
            f"주말/주중 {weekend_to_weekday:.2f}",
        ],
    )
