"""외부 호출 없이 전체 흐름을 돌리기 위한 목업 자료입니다.

프론트엔드가 실제 키 없이도 응답 형태를 보고 화면을 붙일 수 있도록,
그리고 통합 시험이 네트워크 없이 돌 수 있도록 씁니다.
목업도 진짜 오케스트레이터와 중재 에이전트를 그대로 지나갑니다.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.industries.catalog import CATALOG_VERSION
from app.industries.lookup import get
from app.schemas import (
    AgentAnalysis,
    AgentId,
    AnalysisTask,
    MapData,
    MapIndustry,
    MapObservation,
    MapPlace,
    MapQueryResult,
    Scope,
    Site,
)

MOCK_ADDRESS = "서울특별시 송파구 위례광장로 120 155호"
MOCK_SCOPE = Scope(area="서울특별시 송파구 위례광장로 120 일대 반경 500m", period="2026년 2분기")

__all__ = [
    "MOCK_ADDRESS",
    "MOCK_SCOPE",
    "mock_agents",
    "mock_generate",
    "mock_site",
]


def mock_site(address: str | None = None) -> Site:
    """목업 좌표는 고정이고, 보이는 주소만 요청한 값으로 바꿔 줍니다."""
    return Site(
        input_address=(address or MOCK_ADDRESS).strip(),
        road_address="서울특별시 송파구 위례광장로 120",
        detail_address="155호",
        latitude=37.4748,
        longitude=127.1416,
    )


async def mock_resolve(address: str) -> Site:
    return mock_site(address)


def _analysis(task: AnalysisTask, agent_id: AgentId, data: dict[str, Any]) -> AgentAnalysis:
    return AgentAnalysis(
        request_id=task.request_id,
        agent_id=agent_id,
        status="ok",
        scope=MOCK_SCOPE,
        data=data,
    )


async def _floating_population(task: AnalysisTask) -> AgentAnalysis:
    return _analysis(
        task,
        "floating_population",
        {
            "description": "목업 유동인구 자료입니다.",
            "daily_average": 18320,
            "peak_hours": ["12:00-13:00", "18:00-20:00"],
            "office_worker_share": 0.41,
            "resident_share": 0.38,
        },
    )


async def _business_lifecycle(task: AnalysisTask) -> AgentAnalysis:
    return _analysis(
        task,
        "business_lifecycle",
        {
            "description": "목업 개폐업 자료입니다.",
            "industries": [
                {"middle": "한식 음식점업", "open_count": 12, "close_count": 9},
                {"middle": "비알코올 음료점업", "open_count": 18, "close_count": 16},
            ],
        },
    )


async def _commercial_area(task: AnalysisTask) -> AgentAnalysis:
    return _analysis(
        task,
        "commercial_area",
        {
            "description": "목업 상권 자료입니다.",
            "store_total": 1241,
            "by_middle": [
                {"code": "I201", "name": "한식 음식점업", "count": 96, "lq": 1.24},
                {"code": "I212", "name": "비알코올 음료점업", "count": 71, "lq": 2.10},
            ],
        },
    )


def mock_agents() -> dict[AgentId, Any]:
    """세 분석 에이전트를 모두 목업으로 채운 등록표입니다."""
    return {
        "floating_population": _floating_population,
        "business_lifecycle": _business_lifecycle,
        "commercial_area": _commercial_area,
    }


def mock_generate(system_prompt: str, input_json: str) -> dict[str, Any]:
    """중재 모델 호출 자리에 끼우는 고정 응답입니다."""
    return {
        "status": "ok",
        "summary": "점심 직장인 수요가 뚜렷하고 커피·음료는 이미 포화에 가깝습니다.",
        "recommendations": [
            {
                "category": {"major": "음식점업", "middle": "한식 음식점업"},
                "score": 72,
                "reasons": ["직장인 비중이 41%로 점심 수요를 기대할 수 있습니다."],
                "evidence": [
                    {"agent_id": "floating_population", "path": "/office_worker_share"},
                    {"agent_id": "commercial_area", "path": "/by_middle/0"},
                ],
                "risks": ["점포 수가 이미 96개로 경쟁이 적지 않습니다."],
            }
        ],
        "not_recommended": [
            {
                "category": {"major": "음식점업", "middle": "비알코올 음료점업"},
                "score": 28,
                "reasons": ["주변 대비 2.1배로 이미 몰려 있고 폐업도 16건입니다."],
                "evidence": [
                    {"agent_id": "commercial_area", "path": "/by_middle/1"},
                    {"agent_id": "business_lifecycle", "path": "/industries/1"},
                ],
                "risks": ["신규 진입 시 가격 경쟁에 노출됩니다."],
            }
        ],
        "limitations": ["목업 자료로 만든 결과입니다. 실제 판단에 쓰지 마세요."],
    }


def interactive_decision(*, with_map: bool, allow_questions: bool):
    def generate(prompt, payload):
        data = json.loads(payload)
        multi = data.get("analysis_mode") == "multi_agent"
        if (
            multi
            and with_map
            and not any(a["query"]["agent_id"] == "map_analysis" for a in data["answers"])
        ):
            return {
                "action": "ask_specialists",
                "queries": [
                    {
                        "agent_id": "map_analysis",
                        "question": "주변 지하철역을 확인해 주세요.",
                        "why_needed": "접근성 확인",
                        "expected_impact": "교통 근거",
                    }
                ],
            }
        if not multi and with_map and data.get("map_observation") is None:
            return {
                "action": "map_lookup",
                "queries": [
                    {
                        "kind": "infrastructure",
                        "facility_code": "SW8",
                        "why_needed": "목업 교통 접근성 확인",
                        "expected_impact": "접근성 근거 보완",
                    }
                ],
            }
        if allow_questions and data.get("question_fields"):
            return {
                "action": "ask_user",
                "questions": [
                    {
                        "field": "floor",
                        "text": "공실은 몇 층인가요?",
                        "why_needed": "목업 보행 접근성 확인",
                        "expected_impact": "접근 조건 확인",
                    }
                ],
            }
        result = mock_generate(prompt, payload)
        if "evaluation" in data:
            result["evaluation_log"] = [
                {
                    "evaluator": evaluation["evaluator"],
                    "index": comment["index"],
                    "decision": "partial",
                    "applied": "확인할 점에 설비 확인을 추가",
                    "dropped": "설비가 없다고 단정한 부분은 근거가 없어 제외",
                    "reason": "목업",
                }
                for evaluation in data["evaluation"]["evaluations"]
                for comment in evaluation["comments"]
            ]
            if result["recommendations"]:
                result["recommendations"][0]["risks"].append("입점 전 설비를 확인해 주세요.")
        return result

    return generate


async def evaluator(prompt, payload):
    data = json.loads(payload)
    recommendations = data["draft"]["recommendations"]
    if data["evaluator"] != "landlord_advocate" or not recommendations:
        return {"verdict": "agree", "comments": []}
    return {
        "verdict": "conditional",
        "comments": [
            {
                "industry_code": recommendations[0]["category"]["code"],
                "comment": "설비 확인 필요",
                "request": "ask_user" if "ask_user" in data["allowed_requests"] else "none",
            }
        ],
    }


async def specialist(messages, definitions):
    """전문가의 도구 호출·근거 제출도 외부 모델 없이 검증합니다."""
    payload = json.loads(messages[1]["content"])
    if payload["agent_id"] == "map_analysis" and len(messages) == 2:
        codes = payload.get("question", {}).get("industry_codes", [])
        name, arguments = (
            ("search_industry", {"code": codes[0], "query": "카페"})
            if codes
            else ("search_facility", {"code": "SW8"})
        )
    else:
        if payload["agent_id"] == "map_analysis":
            latest = next(
                (json.loads(m["content"]) for m in reversed(messages) if m["role"] == "tool"),
                payload,
            )
            records = [
                {**r, "industry_code": None if code == "_facility" else code}
                for code, rows in latest.get("citations", {}).items()
                for r in rows
            ]
        else:
            facts = payload["facts"]
            records = [
                {"path": parent + "/" + field, "value": value, "industry_code": code}
                for code, groups in [(None, facts["shared"]), *facts["industries"].items()]
                for parent, fields in groups.items()
                for field, value in fields.items()
            ]
        findings = (
            [
                {
                    "claim": "원자료 확인",
                    "signal": "context",
                    "industry_code": records[0]["industry_code"],
                    "evidence": [{"path": records[0]["path"]}],
                }
            ]
            if records
            else []
        )
        name, arguments = (
            "finish",
            {"headline": "목업 전문가 요약", "findings": findings, "limitations": []},
        )
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": "mock",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
            }
        ],
    }


async def map_observation(task, plan):
    queries, places, industries = {}, {}, {}
    for i, q in enumerate(plan.unique_queries(), 1):
        code = q.industry_code
        pid = f"mock-{code}"
        if code:
            places[pid] = MapPlace(name="목업 동종 점포", category_name="목업", distance_m=30)
            industries[code] = MapIndustry(
                name=get(code).name, major=get(code).major_name, place_ids=[pid], sampled_count=1
            )
        queries[f"q{i}"] = MapQueryResult(
            request=q,
            status="ok",
            method="category" if q.facility_code else "keyword",
            category_code=q.facility_code,
            total_count=1 if code else 0,
            has_more=False,
            place_ids=[pid] if code else [],
            matches={pid: "same"} if code else {},
        )
    return MapObservation(
        request_id=task.request_id,
        observation_id=uuid.uuid4().hex,
        site=task.site,
        radius_m=task.radius_m,
        queried_at=datetime.now(UTC).isoformat(),
        master_version=CATALOG_VERSION,
        status="ok" if places else "no_data",
        warnings=["외부 조회 없는 목업입니다."],
        data=MapData(queries=queries, places=places, industries=industries),
    )
