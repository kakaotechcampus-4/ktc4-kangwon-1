import json
from pathlib import Path


# ============================================================
# 기본 설정
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    BASE_DIR
    / "business_lifecycle_agent_output.json"
)

OUTPUT_FILE = (
    BASE_DIR
    / "business_lifecycle_for_mediator.json"
)


# ============================================================
# 1. Agent Output 읽기
# ============================================================

with open(
    INPUT_FILE,
    "r",
    encoding="utf-8",
) as f:

    agent_output = json.load(f)


# ============================================================
# 2. 필요한 값 가져오기
# ============================================================

request_id = agent_output["request_id"]

status = agent_output["status"]

scope = agent_output["scope"]

overall = agent_output["data"]["overall"]

industry_results = (
    agent_output["data"]["industry_results"]
)

warnings = agent_output.get(
    "warnings",
    []
)

error = agent_output.get(
    "error"
)


print("원본 업종 수:", len(industry_results))


# ============================================================
# 3. 중재 Agent용 업종 데이터 생성
#
# 상세 metrics / component_scores는 제거하고
# 최종 판단에 필요한 정보만 전달
# ============================================================

mediator_industries = []


for industry in industry_results:

    mediator_industries.append(
        {
            "industry_id": industry[
                "industry_id"
            ],

            "industry_name": industry[
                "industry_name"
            ],

            "score": industry.get(
                "lifecycle_score"
            ),

            "type": industry.get(
                "type"
            ),

            "confidence": industry.get(
                "confidence"
            ),

            "data_available": industry.get(
                "data_available",
                True,
            ),

            "evidence": industry.get(
                "evidence",
                [],
            ),

            "warning": industry.get(
                "warning"
            ),
        }
    )


# ============================================================
# 4. industry_id 순서 정렬
# ============================================================

mediator_industries = sorted(
    mediator_industries,
    key=lambda x: x["industry_id"],
)


# ============================================================
# 5. 간단 Summary 생성
#
# LLM을 다시 호출하지 않고
# Python에서 사실 기반으로 생성
# ============================================================

available_count = sum(
    1
    for industry in mediator_industries
    if industry["data_available"]
)

unavailable_count = (
    len(mediator_industries)
    - available_count
)


summary = (
    f"{scope['area']}의 "
    f"{scope['period']} 개폐업 데이터를 기준으로 "
    f"총 70개 서비스 업종 중 "
    f"{available_count}개 업종을 분석했습니다. "
    f"{unavailable_count}개 업종은 "
    f"분석 가능한 데이터가 없어 판단 보류 처리했습니다."
)


# ============================================================
# 6. 중재 Agent용 최종 JSON
# ============================================================

mediator_output = {

    "request_id": request_id,

    "agent_id": "business_lifecycle",

    "status": status,

    "scope": {
        "area": scope[
            "area"
        ],

        "area_code": scope[
            "area_code"
        ],

        "period": scope[
            "period"
        ],
    },

    "data": {

        "summary": summary,

        "overall": {
            "open_count": overall[
                "open_count"
            ],

            "close_count": overall[
                "close_count"
            ],

            "net_change": overall[
                "net_change"
            ],
        },

        "coverage": {
            "target_industries": 70,
            "available_industries": (
                available_count
            ),
            "unavailable_industries": (
                unavailable_count
            ),
        },

        "industry_results": (
            mediator_industries
        ),
    },

    "error": error,

    "warnings": warnings,
}


# ============================================================
# 7. JSON 저장
# ============================================================

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        mediator_output,
        f,
        ensure_ascii=False,
        indent=2,
    )


# ============================================================
# 8. 검증
# ============================================================

print()
print("===== Mediator Output 생성 결과 =====")

print(
    "전체 업종:",
    len(mediator_industries)
)

print(
    "데이터 존재 업종:",
    available_count
)

print(
    "데이터 없는 업종:",
    unavailable_count
)

print(
    "전체 개업:",
    overall["open_count"]
)

print(
    "전체 폐업:",
    overall["close_count"]
)

print(
    "전체 순증감:",
    overall["net_change"]
)


# 반드시 70개인지 검증
assert (
    len(mediator_industries)
    == 70
)


# ID 중복 여부 검증
industry_ids = [
    industry["industry_id"]
    for industry in mediator_industries
]

assert (
    len(industry_ids)
    == len(set(industry_ids))
)


print()
print("70개 업종 및 ID 중복 검증 완료")

print()
print("저장 완료:")
print(OUTPUT_FILE)