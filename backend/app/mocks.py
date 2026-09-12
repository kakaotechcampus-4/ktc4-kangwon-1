"""외부 호출 없이 전체 흐름을 돌리기 위한 목업 자료입니다.

프론트엔드가 실제 키 없이도 응답 형태를 보고 화면을 붙일 수 있도록,
그리고 통합 시험이 네트워크 없이 돌 수 있도록 씁니다.
목업도 진짜 오케스트레이터와 중재 에이전트를 그대로 지나갑니다.
"""

from __future__ import annotations

from typing import Any

from app.schemas import AgentAnalysis, AgentId, AnalysisTask, Scope, Site

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
                {"middle": "커피·음료업", "open_count": 18, "close_count": 16},
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
                {"code": "I212", "name": "커피·음료업", "count": 71, "lq": 2.10},
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
                "category": {"major": "음식점업", "middle": "커피·음료업"},
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
