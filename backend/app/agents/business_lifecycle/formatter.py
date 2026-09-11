import json
from pathlib import Path


# =========================================
# 1. 파일 경로
# =========================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_PATH = (
    BASE_DIR
    / "business_lifecycle_agent_output.json"
)

OUTPUT_PATH = (
    BASE_DIR
    / "business_lifecycle_for_mediator.json"
)


# =========================================
# 2. 기존 Agent 결과 읽기
# =========================================

with open(
    INPUT_PATH,
    "r",
    encoding="utf-8"
) as f:

    lifecycle_result = json.load(f)


# =========================================
# 3. 중재 Agent용 업종 데이터 생성
# =========================================

industry_results = []


for industry in lifecycle_result["data"]["industry_scores"]:

    mediator_industry = {

        "industry_code":
            industry["industry_code"],

        "industry_name":
            industry["industry_name"],

        "score":
            industry["score"],

        "type":
            industry["type"],

        "confidence":
            industry["confidence"],

        "evidence":
            industry["evidence"],

        "warning":
            industry["warning"]
    }


    industry_results.append(
        mediator_industry
    )


# =========================================
# 4. 중재 Agent용 최종 JSON
# =========================================

mediator_output = {

    "request_id":
        lifecycle_result["request_id"],

    "agent_id":
        lifecycle_result["agent_id"],

    "status":
        lifecycle_result["status"],

    "scope":
        lifecycle_result["scope"],


    "data": {

        "summary":
            lifecycle_result[
                "data"
            ][
                "summary"
            ],

        "overall":
            lifecycle_result[
                "data"
            ][
                "overall"
            ],

        "industry_results":
            industry_results
    },


    "error":
        lifecycle_result["error"],

    "warnings":
        lifecycle_result["warnings"]
}


# =========================================
# 5. 저장
# =========================================

with open(
    OUTPUT_PATH,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        mediator_output,
        f,
        ensure_ascii=False,
        indent=2
    )


print(
    f"중재 Agent용 JSON 생성 완료"
)

print(
    f"업종 수: {len(industry_results)}"
)

print(
    f"저장 위치: {OUTPUT_PATH}"
)