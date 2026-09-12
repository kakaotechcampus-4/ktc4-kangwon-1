import json
import uuid

import pandas as pd

# =========================================
# 1. 설정
# =========================================

CSV_PATH = "강남역_2024_업종별_개폐업_분석.csv"
OUTPUT_PATH = "gangnam_business_lifecycle_agent_input.json"

AREA_CODE = "3120189"
AREA_NAME = "강남역"

PERIOD = "2024Q1-2024Q4"


# =========================================
# 2. 데이터 불러오기
# =========================================

df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")


# =========================================
# 3. 평균 점포수 계산
# =========================================
# 한 분기의 점포 수만 사용하는 것보다
# Q1~Q4 평균을 사용하는 것이 안정적임

store_columns = [
    "Q1_점포수",
    "Q2_점포수",
    "Q3_점포수",
    "Q4_점포수"
]

df["avg_store_count"] = df[store_columns].mean(axis=1)


# =========================================
# 4. 순증감률 계산
# =========================================
# 단순 순증감은 업종 규모가 크면 값도 커지는 문제가 있음.
#
# 예:
# 300개 점포에서 +20
# 10개 점포에서 +5
#
# 단순 개수로만 보면 +20이 좋아 보이지만,
# 실제 비율로 보면 두 번째 업종의 변화가 훨씬 큼.
#
# 그래서 점포 규모 대비 순증감을 계산함.

df["net_change_rate"] = (
    df["연간_순증감"] / df["avg_store_count"] * 100
)

df["net_change_rate"] = (
    df["net_change_rate"]
    .replace([float("inf"), float("-inf")], 0)
    .fillna(0)
)


# =========================================
# 5. 상대 점수 계산 함수
# =========================================
# 98개 업종끼리 상대적인 위치를 0~100점으로 변환
#
# percentile rank:
# 높을수록 좋은 지표 -> 그대로 사용
# 낮을수록 좋은 지표 -> 역순 사용


def percentile_score(series, higher_is_better=True):

    rank = series.rank(
        pct=True,
        method="average"
    ) * 100

    if higher_is_better:
        return rank

    return 100 - rank


# =========================================
# 6. 개별 지표 점수 계산
# =========================================

# 평균 폐업률
# 낮을수록 좋음
df["close_rate_score"] = percentile_score(
    df["평균_폐업률"],
    higher_is_better=False
)


# 폐업률 변화
#
# 예:
# Q1 6% → Q4 3%
# 변화 = -3
#
# 음수일수록 폐업률 감소 → 좋음
df["close_trend_score"] = percentile_score(
    df["폐업률_Q4_Q1_변화"],
    higher_is_better=False
)


# 순증감률
# 높을수록 좋음
df["net_change_score"] = percentile_score(
    df["net_change_rate"],
    higher_is_better=True
)


# 회전강도
#
# 개업률 + 폐업률
#
# 너무 높은 경우 업종 교체가 빠른 시장이라고 판단
# MVP에서는 낮을수록 안정적이라고 평가
df["turnover_score"] = percentile_score(
    df["평균_회전강도"],
    higher_is_better=False
)


# =========================================
# 7. 최종 Lifecycle Score
# =========================================

df["lifecycle_score"] = (

    df["close_rate_score"] * 0.40

    + df["close_trend_score"] * 0.30

    + df["net_change_score"] * 0.20

    + df["turnover_score"] * 0.10
)


df["lifecycle_score"] = (
    df["lifecycle_score"]
    .round(1)
)


# =========================================
# 8. Confidence 계산
# =========================================
#
# 점포 수가 너무 적으면
# 개폐업 1건에도 비율이 크게 변하기 때문에
# 신뢰도를 낮게 표시

def get_confidence(avg_store_count):

    if avg_store_count >= 20:
        return "high"

    elif avg_store_count >= 5:
        return "medium"

    else:
        return "low"


df["confidence"] = (
    df["avg_store_count"]
    .apply(get_confidence)
)


# =========================================
# 9. Agent에 전달할 업종별 JSON 생성
# =========================================

industries = []


for _, row in df.iterrows():

    industry = {

        "industry_code": row["업종코드"],

        "industry_name": row["업종명"],


        # -----------------------------
        # 실제 원본/가공 지표
        # -----------------------------
        "metrics": {

            "avg_store_count": round(
                float(row["avg_store_count"]), 2
            ),

            "annual_open_count": int(
                row["연간_개업수"]
            ),

            "annual_close_count": int(
                row["연간_폐업수"]
            ),

            "net_change": int(
                row["연간_순증감"]
            ),

            "net_change_rate": round(
                float(row["net_change_rate"]), 2
            ),

            "avg_open_rate": round(
                float(row["평균_개업률"]), 2
            ),

            "avg_close_rate": round(
                float(row["평균_폐업률"]), 2
            ),

            "close_rate_change": round(
                float(row["폐업률_Q4_Q1_변화"]), 2
            ),

            "turnover_rate": round(
                float(row["평균_회전강도"]), 2
            )
        },


        # -----------------------------
        # Python에서 계산한 세부 점수
        # -----------------------------
        "component_scores": {

            "close_rate_score": round(
                float(row["close_rate_score"]), 1
            ),

            "close_trend_score": round(
                float(row["close_trend_score"]), 1
            ),

            "net_change_score": round(
                float(row["net_change_score"]), 1
            ),

            "turnover_score": round(
                float(row["turnover_score"]), 1
            )
        },


        # -----------------------------
        # 최종 점수
        # -----------------------------
        "lifecycle_score": round(
            float(row["lifecycle_score"]), 1
        ),


        # -----------------------------
        # 데이터 신뢰도
        # -----------------------------
        "confidence": row["confidence"]
    }

    industries.append(industry)


# =========================================
# 10. 최종 Agent Input JSON
# =========================================

agent_input = {

    "request_id": str(uuid.uuid4()),

    "analysis_type": "business_lifecycle",

    "area": {

        "area_code": AREA_CODE,

        "area_name": AREA_NAME
    },

    "period": PERIOD,


    # 어떤 방식으로 점수를 만들었는지
    # Agent에게도 알려줌
    "scoring_method": {

        "description":
            "강남역 내 업종 간 상대 순위를 기반으로 계산한 개폐업 안정성 점수",

        "weights": {

            "avg_close_rate": 0.40,

            "close_rate_trend": 0.30,

            "net_change_rate": 0.20,

            "turnover_stability": 0.10
        }
    },


    # 현재 분석 가능한 업종 수
    "coverage": {

        "available_industries": len(industries),

        "target_industries": 100
    },


    # 98개 업종 전체
    "industries": industries
}


# =========================================
# 11. JSON 파일 저장
# =========================================

with open(
    OUTPUT_PATH,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        agent_input,
        f,
        ensure_ascii=False,
        indent=2
    )


print(
    f"{len(industries)}개 업종 JSON 생성 완료"
)

print(
    f"저장 파일: {OUTPUT_PATH}"
)

# =========================================
# 점수 결과 확인
# =========================================

print("\n===== Lifecycle Score TOP 10 =====")

print(
    df[
        [
            "업종코드",
            "업종명",
            "lifecycle_score",
            "평균_폐업률",
            "폐업률_Q4_Q1_변화",
            "net_change_rate"
        ]
    ]
    .sort_values(
        "lifecycle_score",
        ascending=False
    )
    .head(10)
    .to_string(index=False)
)


print("\n===== Lifecycle Score BOTTOM 10 =====")

print(
    df[
        [
            "업종코드",
            "업종명",
            "lifecycle_score",
            "평균_폐업률",
            "폐업률_Q4_Q1_변화",
            "net_change_rate"
        ]
    ]
    .sort_values(
        "lifecycle_score",
        ascending=True
    )
    .head(10)
    .to_string(index=False)
)