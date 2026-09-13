import json
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

# ============================================================
# 기본 설정
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    BASE_DIR
    / "개롱역_2025Q2_70업종_점수결과.csv"
)

OUTPUT_FILE = (
    BASE_DIR
    / "business_lifecycle_agent_input.json"
)


AREA_CODE = "3120240"
AREA_NAME = "개롱역"
PERIOD = "2025Q2"


# ============================================================
# Lifecycle Score 설정
# ============================================================

SCORING_METHOD: dict[str, Any] = {
    "description": (
        "개롱역 2025년 2분기 데이터가 존재하는 업종 간 "
        "상대 순위를 기반으로 계산한 개폐업 안정성 점수"
    ),
    "score_type": "relative",
    "weights": {
        "close_rate": 0.50,
        "net_change_rate": 0.30,
        "turnover_stability": 0.20,
    },
    "notes": [
        "lifecycle_score는 미래 생존 확률이 아니다.",
        "데이터가 존재하는 업종끼리 상대 비교한 점수이다.",
        "폐업률이 낮을수록 높은 점수를 받는다.",
        "순증감률이 높을수록 높은 점수를 받는다.",
        "개업률과 폐업률을 합한 회전율이 낮을수록 안정적으로 평가한다.",
    ],
}


# ============================================================
# 숫자 변환 함수
#
# pandas / numpy 타입을 JSON에서 안전하게 사용할 수 있도록 변환
# ============================================================

def to_int(value):
    if pd.isna(value):
        return None

    return int(value)


def to_float(value):
    if pd.isna(value):
        return None

    return float(value)


def to_bool(value):
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() == "true"

    return bool(value)


# ============================================================
# 1. 점수 결과 CSV 읽기
# ============================================================

df = pd.read_csv(
    INPUT_FILE,
    encoding="utf-8-sig",
)


print("전체 서비스 업종 수:", len(df))


# ============================================================
# 2. data_available 안전하게 정리
# ============================================================

df["data_available"] = (
    df["data_available"]
    .apply(to_bool)
)


# ============================================================
# 3. 실제 분석 가능한 업종
#
# GPT Agent에는 lifecycle_score가 존재하는 업종만 전달
# ============================================================

available_df = df[
    df["data_available"]
    & df["lifecycle_score"].notna()
].copy()


# ============================================================
# 4. 데이터가 없는 업종
#
# 이 업종들은 GPT에게 보내지 않는다.
# 최종 결과에서 판단 보류 처리하기 위해 별도로 저장
# ============================================================

unavailable_df = df[
    ~(
        df["data_available"]
        & df["lifecycle_score"].notna()
    )
].copy()


print(
    "Agent 분석 대상 업종 수:",
    len(available_df)
)

print(
    "데이터 없는 업종 수:",
    len(unavailable_df)
)


# ============================================================
# 5. Agent 분석 대상 업종 JSON 생성
# ============================================================

industries: list[dict[str, Any]] = []


for _, row in available_df.iterrows():

    industry = {
        "industry_id": to_int(
            row["service_id"]
        ),

        "industry_name": row[
            "service_name"
        ],

        "metrics": {
            "store_count": to_int(
                row["store_count"]
            ),

            "open_count": to_int(
                row["open_count"]
            ),

            "close_count": to_int(
                row["close_count"]
            ),

            "open_rate": to_float(
                row["open_rate"]
            ),

            "close_rate": to_float(
                row["close_rate"]
            ),

            "net_change": to_int(
                row["net_change"]
            ),

            "net_change_rate": to_float(
                row["net_change_rate"]
            ),

            "turnover_rate": to_float(
                row["turnover_rate"]
            ),
        },

        "component_scores": {
            "close_rate_score": to_float(
                row["close_rate_score"]
            ),

            "net_change_score": to_float(
                row["net_change_score"]
            ),

            "turnover_score": to_float(
                row["turnover_score"]
            ),
        },

        "lifecycle_score": to_float(
            row["lifecycle_score"]
        ),

        "confidence": row[
            "confidence"
        ],
    }

    industries.append(industry)


# ============================================================
# 6. 데이터 없는 업종 JSON 생성
# ============================================================

unavailable_industries: list[dict[str, Any]] = []


for _, row in unavailable_df.iterrows():

    missing_reason = row.get(
        "missing_reason"
    )

    if pd.isna(missing_reason):
        missing_reason = (
            "분석 가능한 개폐업 데이터 없음"
        )

    unavailable_industries.append(
        {
            "industry_id": to_int(
                row["service_id"]
            ),

            "industry_name": row[
                "service_name"
            ],

            "data_available": False,

            "missing_reason": str(
                missing_reason
            ),
        }
    )


# ============================================================
# 7. Agent 입력 전체 JSON
# ============================================================

agent_input: dict[str, Any] = {

    "request_id": str(uuid.uuid4()),

    "analysis_type": "business_lifecycle",

    "scope": {
        "area_code": AREA_CODE,
        "area_name": AREA_NAME,
        "period": PERIOD,
    },

    "scoring_method": SCORING_METHOD,

    "coverage": {
        "target_industries": 70,
        "available_industries": len(
            available_df
        ),
        "unavailable_industries": len(
            unavailable_df
        ),
        "analyzed_industries": len(
            available_df
        ),
    },

    # GPT가 실제 분석할 업종
    "industries": industries,

    # GPT 분석에서는 제외
    "unavailable_industries": (
        unavailable_industries
    ),
}


# ============================================================
# 8. JSON 저장
# ============================================================

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        agent_input,
        f,
        ensure_ascii=False,
        indent=2,
    )


# ============================================================
# 9. 검증
# ============================================================

print()
print("===== Agent Input 생성 결과 =====")

print(
    "전체 목표 업종:",
    agent_input["coverage"][
        "target_industries"
    ],
)

print(
    "Agent 분석 대상:",
    agent_input["coverage"][
        "available_industries"
    ],
)

print(
    "데이터 없는 업종:",
    agent_input["coverage"][
        "unavailable_industries"
    ],
)


# 분석 대상 + 데이터 없음 = 70인지 검증
assert (
    agent_input["coverage"][
        "available_industries"
    ]
    + agent_input["coverage"][
        "unavailable_industries"
    ]
    == 70
)


# 실제 industries 개수 검증
assert (
    len(agent_input["industries"])
    == agent_input["coverage"][
        "available_industries"
    ]
)


print()
print("검증 완료")

print()
print("저장 완료:")
print(OUTPUT_FILE)