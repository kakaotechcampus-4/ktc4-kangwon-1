"""공개 목업도 동일한 도구 루프·평가자·보고서 검증을 거칩니다."""

import json

from openai.types.chat import ChatCompletionMessage

from app.schemas import Site


def call(name, arguments):
    return ChatCompletionMessage(
        role="assistant",
        tool_calls=[
            {
                "id": "mock-call",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
            }
        ],
    )


def generators(*, ask=False):
    async def decision(messages, definitions, settings, receipt):
        receipt.update(model="mock", usage={"prompt_tokens": 0, "completion_tokens": 0})
        if ask and len(messages) == 2:
            return call(
                "ask_user",
                {
                    "questions": [
                        {"field": "floor", "question": "몇 층인가요?", "reason": "공간 조건 확인"}
                    ]
                },
            )
        if "submit_l" in {d["function"]["name"] for d in definitions}:
            return call("submit_l", {"L_records": [], "finish": True})
        final = any(m["role"] == "user" and '"reviews"' in m.get("content", "") for m in messages)
        return call(
            "submit_draft",
            {
                "phase": "final" if final else "draft",
                "report": {
                    "summary_segments": [{"type": "text", "text": "목업 자료로 검토한 결과입니다."}]
                },
            },
        )

    async def evaluator(messages, definitions, settings, receipt):
        receipt.update(model="mock", usage={"prompt_tokens": 0, "completion_tokens": 0})
        packet = json.loads(messages[1]["content"])
        return call(
            "submit_review", {"draft_id": packet["draft_id"], "verdict": "agree", "issues": []}
        )

    return {"generate": decision, "evaluator_generate": evaluator}


def dependencies(*, ask=False):
    async def resolve(address):
        return Site(input_address=address, road_address=address, latitude=37.552, longitude=126.925)

    return {"resolve": resolve, "mock": True, **generators(ask=ask)}


def building_registry():
    """외부 호출 없는 건축물대장 대역입니다. 화면 연동용이며 주소와 상관없이 같습니다.

    성희프라자 10/13 실호출 응답에서 일부 행만 옮겼습니다. 층별개요는 19행 중 지하 1층과
    4층 4행, 호실은 83개 중 4층 3개입니다. 나머지 값은 실호출 그대로입니다.
    """
    from app.building_registry import (
        BuildingRegistry,
        BuildingTitle,
        FloorOverview,
        SewageFacility,
        Unit,
    )

    return BuildingRegistry(
        road_address="서울 송파구 위례광장로 199",
        jibun_address="서울 송파구 장지동 880-1",
        titles=[
            BuildingTitle(
                dong_name=None,
                building_name="성희프라자",
                main_use="제2종근린생활시설",
                ground_floors=7,
                underground_floors=2,
                total_area_m2=12301.78,
                parking_spaces=82,
            )
        ],
        floors=[
            FloorOverview(
                dong_name=None,
                floor="지하 1층",
                use="기타제2종근린생활시설",
                use_detail="지하주차장/MDF실/방재센터",
                area_m2=1925.34,
            ),
            FloorOverview(
                dong_name=None,
                floor="4층",
                use="일반음식점",
                use_detail="제2종근린생활시설",
                area_m2=275.49,
            ),
            FloorOverview(
                dong_name=None,
                floor="4층",
                use="의원",
                use_detail="제1종근린생활시설",
                area_m2=498.12,
            ),
            FloorOverview(
                dong_name=None, floor="4층", use="사무소", use_detail="업무시설", area_m2=220.8
            ),
            FloorOverview(
                dong_name=None, floor="4층", use="학원", use_detail="교육연구시설", area_m2=252.59
            ),
        ],
        units=[
            Unit(
                dong_name=None,
                unit_name="401호",
                floor="4층",
                use="학원",
                use_detail="교육연구시설(학원)",
                area_m2=100.8,
            ),
            Unit(
                dong_name=None,
                unit_name="404호",
                floor="4층",
                use="의원",
                use_detail="제1종근린생활시설(의원)",
                area_m2=93.6,
            ),
            Unit(
                dong_name=None,
                unit_name="410호",
                floor="4층",
                use="일반음식점",
                use_detail="제2종근린생활시설(일반음식점)",
                area_m2=57.04,
            ),
        ],
        sewage=[SewageFacility(method="하수종말처리장 연결", method_name="하수종말처리장연결")],
    )
