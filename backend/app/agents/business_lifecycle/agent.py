import json
import os
from pathlib import Path

from openai import OpenAI


# ============================================================
# 기본 설정
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    BASE_DIR
    / "business_lifecycle_agent_input.json"
)

OUTPUT_FILE = (
    BASE_DIR
    / "business_lifecycle_agent_output.json"
)


MODEL_NAME = "gpt-5.6-luna"

# 한 번에 너무 많은 업종을 보내지 않도록 나눠서 요청
BATCH_SIZE = 20


# ============================================================
# Elice MLAPI 설정
# ============================================================

client = OpenAI(
    base_url=(
        "https://mlapi.run/"
        "286e9158-d32e-436d-a23d-36b43fc8e68a/v1"
    ),
    api_key=os.environ["ELICE_MLAPI_KEY"],
)


# ============================================================
# System Prompt
# ============================================================

SYSTEM_PROMPT = """
당신은 상권의 업종별 개폐업 상태를 해석하는
Business Lifecycle Agent입니다.

입력 데이터는 서울시 상권분석서비스의
2025년 2분기 개폐업 데이터를 기반으로
Python에서 미리 계산된 결과입니다.

당신의 역할은 숫자를 새로 계산하는 것이 아니라,
입력된 지표를 바탕으로 업종의 현재 개폐업 상태를
간결하게 해석하는 것입니다.


[매우 중요한 제한사항]

1. 입력 JSON에 없는 정보를 사용하지 마십시오.

2. 유동인구, 매출, 임대료, 경쟁업체 수,
   상권 이미지, 소비자 선호 등 다른 정보를
   추측하지 마십시오.

3. lifecycle_score,
   component_scores,
   metrics의 숫자를 수정하거나 다시 계산하지 마십시오.

4. lifecycle_score는 미래 생존확률이 아닙니다.

5. lifecycle_score는
   개롱역 2025년 2분기의 분석 가능한 업종끼리
   상대적으로 비교한 '개폐업 안정성 점수'입니다.

6. 데이터는 2025년 2분기 단일 기간 데이터입니다.
   따라서 다음과 같은 시계열 표현을 사용하면 안 됩니다.

   - 최근 개선되고 있다
   - 계속 악화되고 있다
   - 증가 추세다
   - 감소 추세다
   - 앞으로 성장할 것이다

7. 미래의 생존확률이나 성공확률을 예측하지 마십시오.

8. confidence가 "low"인 경우,
   점포 표본 수가 적어 해석에 주의가 필요하다는
   warning을 반드시 작성하십시오.


[지표 의미]

store_count:
해당 업종의 점포 수

open_count:
2025년 2분기 개업 점포 수

close_count:
2025년 2분기 폐업 점포 수

open_rate:
개업 점포 수 / 전체 점포 수

close_rate:
폐업 점포 수 / 전체 점포 수

net_change:
개업 점포 수 - 폐업 점포 수

net_change_rate:
net_change / 전체 점포 수

turnover_rate:
open_rate + close_rate

lifecycle_score:
개폐업 안정성 상대점수

confidence:
점포 수를 기준으로 계산한 데이터 신뢰도


[유형]

각 업종에는 반드시 아래 5가지 중 하나만 부여하십시오.

1. 성장·안정형
- 개업이 폐업보다 많으며
- 폐업률이 상대적으로 낮거나 안정적인 경우

2. 안정 유지형
- 개업과 폐업이 모두 적거나
- 순증감이 크지 않고 회전율이 낮은 경우

3. 과열·회전형
- 개업과 폐업이 모두 활발하거나
- 회전율이 상대적으로 높은 경우

4. 쇠퇴·위험형
- 폐업이 개업보다 많고
- 폐업률이 상대적으로 높은 경우

5. 판단 보류
- 지표가 서로 크게 충돌하거나
- 신뢰도가 지나치게 낮아 명확한 유형 판단이 어려운 경우


[evidence 작성]

각 업종마다 evidence를 2~3개 작성하십시오.

반드시 입력된 실제 숫자를 사용하십시오.

좋은 예:
- "2025년 2분기 개업 6건, 폐업 4건으로 순증감은 +2건입니다."
- "폐업률은 7.27%, 순증감률은 3.64%입니다."
- "개업률과 폐업률을 합한 회전율은 18.18%입니다."

나쁜 예:
- "상권 특성상 인기가 많은 업종입니다."
- "앞으로 성장할 가능성이 높습니다."
- "유동인구가 많아 유리합니다."

입력 데이터에 없는 내용이기 때문입니다.


[warning]

특별한 주의사항이 없으면 null을 사용하십시오.

confidence가 low이면 반드시 다음 취지의 경고를 포함하십시오.

"점포 수가 적어 분기별 개폐업 수치의 변동성이 클 수 있습니다."


[출력 형식]

반드시 JSON만 출력하십시오.
Markdown 코드블록을 사용하지 마십시오.
설명 문장을 JSON 밖에 작성하지 마십시오.

형식:

{
  "industry_interpretations": [
    {
      "industry_id": 1,
      "type": "성장·안정형",
      "evidence": [
        "근거 1",
        "근거 2"
      ],
      "warning": null
    }
  ]
}
"""


# ============================================================
# JSON 응답 파싱
# ============================================================

def parse_json_response(text):
    """
    모델이 혹시 ```json ... ``` 형태로 반환해도
    안전하게 JSON 부분만 추출한다.
    """

    text = text.strip()

    if text.startswith("```json"):
        text = text[len("```json"):]

    elif text.startswith("```"):
        text = text[len("```"):]

    if text.endswith("```"):
        text = text[:-3]

    text = text.strip()

    return json.loads(text)


# ============================================================
# Batch 분리
# ============================================================

def split_batches(items, batch_size):
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]


# ============================================================
# GPT 분석
# ============================================================

def analyze_batch(batch):
    """
    한 batch의 업종들을 GPT에게 전달하고
    해석 결과를 반환한다.
    """

    user_payload = {
        "period": "2025Q2",
        "industries": batch,
    }

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    user_payload,
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ],
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

    return result[
        "industry_interpretations"
    ]


# ============================================================
# 1. Agent Input 읽기
# ============================================================

with open(
    INPUT_FILE,
    "r",
    encoding="utf-8",
) as f:

    agent_input = json.load(f)


industries = agent_input[
    "industries"
]

unavailable_industries = agent_input[
    "unavailable_industries"
]


print(
    "Agent 분석 대상 업종:",
    len(industries)
)

print(
    "데이터 없는 업종:",
    len(unavailable_industries)
)


# ============================================================
# 2. GPT Batch 분석
# ============================================================

all_interpretations = []


batches = list(
    split_batches(
        industries,
        BATCH_SIZE,
    )
)


print()
print(
    "API 호출 횟수:",
    len(batches)
)


for batch_index, batch in enumerate(
    batches,
    start=1,
):

    print(
        f"[{batch_index}/{len(batches)}] "
        f"{len(batch)}개 업종 분석 중..."
    )

    interpretations = analyze_batch(
        batch
    )

    all_interpretations.extend(
        interpretations
    )


# ============================================================
# 3. 결과 개수 검증
# ============================================================

print()
print(
    "GPT 분석 결과 개수:",
    len(all_interpretations)
)


if len(all_interpretations) != len(industries):

    print(
        "경고: 입력 업종 수와 "
        "GPT 결과 업종 수가 다릅니다."
    )


# ============================================================
# 4. industry_id 기준 해석 결과 Dictionary
# ============================================================

interpretation_map = {
    item["industry_id"]: item
    for item in all_interpretations
}


# ============================================================
# 5. 실제 데이터가 있는 업종 결과 결합
# ============================================================

industry_results = []


for industry in industries:

    industry_id = industry[
        "industry_id"
    ]

    interpretation = (
        interpretation_map.get(
            industry_id
        )
    )


    if interpretation is None:

        industry_results.append(
            {
                **industry,

                "type": "판단 보류",

                "evidence": [],

                "warning": (
                    "LLM 분석 결과를 "
                    "받지 못했습니다."
                ),
            }
        )

        continue


    industry_results.append(
        {
            **industry,

            "type": interpretation[
                "type"
            ],

            "evidence": interpretation[
                "evidence"
            ],

            "warning": interpretation.get(
                "warning"
            ),
        }
    )


# ============================================================
# 6. 데이터 없는 19개 업종 추가
#
# GPT에 보내지 않고 Python에서 판단 보류 처리
# ============================================================

for industry in unavailable_industries:

    industry_results.append(
        {
            "industry_id": industry[
                "industry_id"
            ],

            "industry_name": industry[
                "industry_name"
            ],

            "data_available": False,

            "metrics": None,

            "component_scores": None,

            "lifecycle_score": None,

            "confidence": "none",

            "type": "판단 보류",

            "evidence": [],

            "warning": industry[
                "missing_reason"
            ],
        }
    )


# ============================================================
# 7. ID 순서 정렬
# ============================================================

industry_results = sorted(
    industry_results,
    key=lambda x: x["industry_id"],
)


# ============================================================
# 8. 전체 개폐업 통계
#
# 실제 데이터가 있는 업종만 합산
# ============================================================

overall_open_count = sum(
    industry["metrics"]["open_count"]
    for industry in industries
)

overall_close_count = sum(
    industry["metrics"]["close_count"]
    for industry in industries
)

overall_net_change = (
    overall_open_count
    - overall_close_count
)


# ============================================================
# 9. 최종 Agent Output
# ============================================================

agent_output = {

    "request_id": agent_input[
        "request_id"
    ],

    "agent_id": "business_lifecycle",

    "status": "ok",

    "scope": {
        "area": agent_input[
            "scope"
        ]["area_name"],

        "area_code": agent_input[
            "scope"
        ]["area_code"],

        "period": agent_input[
            "scope"
        ]["period"],
    },

    "data": {

        "coverage": agent_input[
            "coverage"
        ],

        "scoring_method": agent_input[
            "scoring_method"
        ],

        "overall": {
            "open_count": (
                overall_open_count
            ),

            "close_count": (
                overall_close_count
            ),

            "net_change": (
                overall_net_change
            ),
        },

        "industry_results": (
            industry_results
        ),
    },

    "error": None,

    "warnings": [
        (
            "2025년 2분기 단일 분기 데이터를 "
            "기준으로 한 상대적 개폐업 안정성 분석입니다."
        ),
        (
            "lifecycle_score는 미래 생존확률이나 "
            "사업 성공확률을 의미하지 않습니다."
        ),
        (
            "분기 단위 데이터 특성상 개업·폐업이 "
            "발생하지 않은 업종이 많아 "
            "동일하거나 유사한 점수가 나타날 수 있습니다."
        ),
    ],
}


# ============================================================
# 10. JSON 저장
# ============================================================

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        agent_output,
        f,
        ensure_ascii=False,
        indent=2,
    )


# ============================================================
# 11. 최종 검증
# ============================================================

print()
print("===== Agent 실행 완료 =====")

print(
    "최종 업종 수:",
    len(industry_results)
)

print(
    "개업 합계:",
    overall_open_count
)

print(
    "폐업 합계:",
    overall_close_count
)

print(
    "순증감:",
    overall_net_change
)


assert len(industry_results) == 70


print()
print("70개 업종 검증 완료")

print()
print("저장 완료:")
print(OUTPUT_FILE)