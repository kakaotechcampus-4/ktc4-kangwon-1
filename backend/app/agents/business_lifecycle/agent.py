import json
import os
import re
from pathlib import Path

from openai import OpenAI

# ============================================================
# 1. 기본 설정
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_PATH = (
    BASE_DIR
    / "gangnam_business_lifecycle_agent_input.json"
)

OUTPUT_PATH = (
    BASE_DIR
    / "business_lifecycle_agent_output.json"
)


# 엘리스 GPT-5.6 Luna endpoint
BASE_URL = (
    "https://mlapi.run/"
    "286e9158-d32e-436d-a23d-36b43fc8e68a/v1"
)

MODEL_NAME = "gpt-5.6-luna"

# 한 번에 분석할 업종 수
BATCH_SIZE = 20


# ============================================================
# 2. API Key 확인
# ============================================================

API_KEY = os.environ.get("ELICE_MLAPI_KEY")

if not API_KEY:
    raise RuntimeError(
        "ELICE_MLAPI_KEY 환경변수가 없습니다.\n"
        "PowerShell에서 먼저 다음 명령을 실행하세요:\n"
        '$env:ELICE_MLAPI_KEY="발급받은_API_KEY"'
    )


# ============================================================
# 3. 엘리스 MLAPI Client
# ============================================================

client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
)


# ============================================================
# 4. System Prompt
# ============================================================

SYSTEM_PROMPT = """
너는 서울시 상권의 업종별 개업·폐업 데이터를 분석하는
Business Lifecycle Agent다.

반드시 입력 JSON에 포함된 데이터만 사용한다.

유동인구, 매출, 임대료, 주변 경쟁업체 수, 소비자 선호 등
입력에 없는 정보는 추측하지 않는다.

너의 역할은 Python에서 미리 계산된 개폐업 지표를 해석하는 것이다.

[중요 규칙]

1. lifecycle_score를 다시 계산하거나 수정하지 않는다.
2. component_scores를 다시 계산하거나 수정하지 않는다.
3. 입력된 숫자를 임의로 변경하지 않는다.
4. 입력에 없는 새로운 숫자를 만들지 않는다.
5. lifecycle_score는 해당 상권 내 업종 간 상대평가 점수이다.
6. 이 점수를 성공확률이나 생존확률로 표현하지 않는다.
7. net_change가 양수이면 개업이 폐업보다 많은 것이다.
8. net_change가 음수이면 폐업이 개업보다 많은 것이다.
9. close_rate_change가 음수이면 폐업률이 개선된 것이다.
10. close_rate_change가 양수이면 폐업률이 악화된 것이다.
11. turnover_rate가 높다고 무조건 긍정적으로 판단하지 않는다.
12. confidence가 low이면 표본 수가 적어 변동성이 클 수 있음을 언급한다.
13. 입력된 모든 업종을 빠짐없이 각각 한 번씩 분석한다.
14. 최종적인 업종 추천이나 비추천을 하지 않는다.

[유형]

각 업종을 반드시 다음 5개 중 하나로 분류한다.

- 성장·안정형
- 안정 유지형
- 과열·회전형
- 쇠퇴·위험형
- 판단 보류

[근거]

각 업종마다 evidence를 2~3개 작성한다.

가능하면 실제 입력 수치를 사용한다.

예:
- "연간 개업 98건, 폐업 57건으로 순증감 +41건"
- "Q1 대비 Q4 폐업률이 2%p 감소"
- "평균 폐업률은 3.25%"

[출력]

반드시 아래 JSON 형식으로만 응답한다.

{
  "industry_interpretations": [
    {
      "industry_code": "CS100001",
      "type": "성장·안정형",
      "evidence": [
        "근거1",
        "근거2"
      ],
      "warning": null
    }
  ]
}

JSON 외의 설명, 마크다운, 코드블록은 작성하지 않는다.
"""


# ============================================================
# 5. 입력 JSON 읽기
# ============================================================

with open(
    INPUT_PATH,
    encoding="utf-8",
) as f:
    agent_input = json.load(f)


industries = agent_input["industries"]

print(f"입력 업종 수: {len(industries)}")


# ============================================================
# 6. 모델 응답에서 JSON 추출
# ============================================================

def parse_json_response(text):

    text = text.strip()

    # ```json ... ``` 형태로 왔을 경우 제거
    text = re.sub(
        r"^```json\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"^```\s*",
        "",
        text,
    )

    text = re.sub(
        r"\s*```$",
        "",
        text,
    )

    return json.loads(text)


# ============================================================
# 7. 20개씩 나누어 Agent 호출
# ============================================================

interpretations = {}

failed_batches = []


for start in range(
    0,
    len(industries),
    BATCH_SIZE,
):

    batch = industries[
        start : start + BATCH_SIZE
    ]

    batch_number = (
        start // BATCH_SIZE
    ) + 1

    print(
        f"\n[{batch_number}] "
        f"{start + 1} ~ "
        f"{start + len(batch)}번째 업종 분석 중..."
    )


    user_data = {
        "area": agent_input["area"],
        "period": agent_input["period"],
        "industries": batch,
    }


    try:

        response = (
            client.chat.completions.create(
                model=MODEL_NAME,

                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": (
                            "다음 업종 데이터를 분석하세요.\n\n"
                            + json.dumps(
                                user_data,
                                ensure_ascii=False,
                            )
                        ),
                    },
                ],
            )
        )


        response_text = (
            response
            .choices[0]
            .message
            .content
        )


        result = parse_json_response(
            response_text
        )


        batch_results = result[
            "industry_interpretations"
        ]


        for item in batch_results:

            code = item[
                "industry_code"
            ]

            # 동일 코드 중복 방지
            if code not in interpretations:
                interpretations[code] = item


        print(
            f"→ {len(batch_results)}개 "
            f"업종 분석 완료"
        )


    except Exception as e:

        print(
            f"→ 배치 분석 실패: {e}"
        )

        failed_batches.append({
            "batch_number": batch_number,
            "error": str(e),
        })


# ============================================================
# 8. Python 계산값 + Agent 해석 합치기
# ============================================================

industry_scores = []

missing_codes = []


for industry in industries:

    code = industry[
        "industry_code"
    ]

    interpretation = (
        interpretations.get(code)
    )


    if interpretation is None:

        missing_codes.append(code)

        continue


    result = {

        "industry_code":
            industry[
                "industry_code"
            ],

        "industry_name":
            industry[
                "industry_name"
            ],

        # Python에서 만든 점수
        "score":
            industry[
                "lifecycle_score"
            ],

        # LLM이 판단한 유형
        "type":
            interpretation[
                "type"
            ],

        "confidence":
            industry[
                "confidence"
            ],

        # 실제 지표
        "metrics":
            industry[
                "metrics"
            ],

        # 세부 점수도 유지
        "component_scores":
            industry[
                "component_scores"
            ],

        # LLM 설명
        "evidence":
            interpretation[
                "evidence"
            ],

        "warning":
            interpretation.get(
                "warning"
            ),
    }


    industry_scores.append(
        result
    )


# ============================================================
# 9. TOP / BOTTOM 5
# ============================================================

sorted_industries = sorted(
    industry_scores,
    key=lambda x: x["score"],
    reverse=True,
)


top_industries = [
    {
        "industry_code":
            item["industry_code"],

        "industry_name":
            item["industry_name"],

        "score":
            item["score"],

        "type":
            item["type"],

        "evidence":
            item["evidence"],
    }

    for item
    in sorted_industries[:5]
]


bottom_industries = [
    {
        "industry_code":
            item["industry_code"],

        "industry_name":
            item["industry_name"],

        "score":
            item["score"],

        "type":
            item["type"],

        "evidence":
            item["evidence"],
    }

    for item
    in sorted_industries[-5:][::-1]
]


# ============================================================
# 10. 전체 개폐업 수 계산
# ============================================================

total_open = sum(
    industry["metrics"][
        "annual_open_count"
    ]
    for industry in industries
)


total_close = sum(
    industry["metrics"][
        "annual_close_count"
    ]
    for industry in industries
)


total_net_change = (
    total_open
    - total_close
)


# ============================================================
# 11. Summary 생성
# ============================================================

summary = (
    f"{agent_input['area']['area_name']} 상권의 "
    f"{agent_input['period']} 개폐업 데이터를 분석한 결과, "
    f"분석 가능한 업종은 총 {len(industry_scores)}개입니다. "
    f"연간 개업은 {total_open}건, "
    f"폐업은 {total_close}건으로 "
    f"순증감은 {total_net_change:+d}건입니다. "
    f"업종별 lifecycle_score는 해당 상권 내 업종끼리의 "
    f"상대적인 개폐업 안정성을 나타냅니다."
)


# ============================================================
# 12. 중재 Agent용 공통 포맷
# ============================================================

warnings = [
    (
        "2024년 한 해 데이터만 사용하므로 "
        "장기적인 업종 생존성을 의미하지 않음"
    ),

    (
        "개폐업 데이터만을 이용한 분석이며 "
        "유동인구·경쟁업체·매출은 반영하지 않음"
    ),
]


if missing_codes:

    warnings.append(
        "Agent 해석이 누락된 업종 코드: "
        + ", ".join(missing_codes)
    )


if failed_batches:

    warnings.append(
        "일부 API 배치 호출이 실패함"
    )


if len(industry_scores) == len(industries):

    status = "ok"

elif len(industry_scores) > 0:

    status = "partial"

else:

    status = "error"


final_output = {

    "request_id":
        agent_input[
            "request_id"
        ],

    "agent_id":
        "business_lifecycle",

    "status":
        status,

    "scope": {

        "area":
            agent_input[
                "area"
            ][
                "area_name"
            ] + " 상권",

        "area_code":
            agent_input[
                "area"
            ][
                "area_code"
            ],

        "period":
            agent_input[
                "period"
            ],
    },

    "data": {

        "coverage": {

            "target_industries":
                agent_input[
                    "coverage"
                ][
                    "target_industries"
                ],

            "available_industries":
                agent_input[
                    "coverage"
                ][
                    "available_industries"
                ],

            "analyzed_industries":
                len(
                    industry_scores
                ),
        },

        "overall": {

            "annual_open_count":
                total_open,

            "annual_close_count":
                total_close,

            "net_change":
                total_net_change,
        },

        "summary":
            summary,

        # 전체 업종
        "industry_scores":
            industry_scores,

        # 요약용
        "top_industries":
            top_industries,

        "bottom_industries":
            bottom_industries,
    },

    "error":
        None
        if status != "error"
        else {
            "code":
                "AGENT_EXECUTION_ERROR",

            "message":
                "모든 업종 분석에 실패했습니다.",
        },

    "warnings":
        warnings,
}


# ============================================================
# 13. JSON 저장
# ============================================================

with open(
    OUTPUT_PATH,
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        final_output,
        f,
        ensure_ascii=False,
        indent=2,
    )


# ============================================================
# 14. 결과 출력
# ============================================================

print("\n===================================")

print(
    f"Agent 상태: "
    f"{final_output['status']}"
)

print(
    f"분석된 업종 수: "
    f"{len(industry_scores)}"
)

print(
    f"누락 업종 수: "
    f"{len(missing_codes)}"
)

print(
    f"결과 저장 위치:\n"
    f"{OUTPUT_PATH}"
)

print("===================================")