"""외부 호출 없이 전체 흐름을 돌리기 위한 목업 자료입니다.

프론트엔드가 실제 키 없이도 응답 형태를 보고 화면을 붙일 수 있도록,
그리고 통합 시험이 네트워크 없이 돌 수 있도록 씁니다.
목업도 진짜 오케스트레이터와 중재 에이전트를 그대로 지나갑니다.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from app.agents.business_lifecycle.schemas import BusinessLifecycleData
from app.agents.commercial_area.schemas import (
    CommercialAreaData,
    Diversity,
    LqBaseline,
    RestaurantDensity,
)
from app.agents.floating_population.schemas import FloatingPopulationData
from app.evidence import scalar_records
from app.industries import TAXONOMY, lookup
from app.schemas import AgentAnalysis, AgentId, AnalysisTask, Scope, Site

MOCK_ADDRESS = "서울특별시 송파구 위례광장로 120 155호"
MOCK_SCOPE = Scope(area="서울특별시 송파구 위례광장로 120 일대 반경 500m", period="2026년 2분기")

__all__ = [
    "MOCK_ADDRESS",
    "MOCK_SCOPE",
    "mock_agents",
    "mock_business_lifecycle_data",
    "mock_commercial_area_data",
    "mock_floating_population_data",
    "mock_generate",
    "mock_site",
]


def _middle(code: str, count: int, lq: float) -> dict[str, Any]:
    industry = lookup.get(code)
    return {
        "code": code,
        "name": industry.name,
        "major_code": industry.major_code,
        "major_name": industry.major_name,
        "count": count,
        "share": round(count / 1241, 4),
        "density_per_km2": round(count / 0.785, 2),
        "lq": lq,
        "lq_district": None,
        "diff_type_count": 1,
        "jacobian": 0.5,
        "major_cluster_count": count,
        "major_cluster_diversity": 0.5,
    }


def mock_commercial_area_data() -> dict[str, Any]:
    return CommercialAreaData.model_validate(
        {
            "description": "목업 상권 자료입니다.",
            "radius_m": 500,
            "store_total": 1241,
            "by_middle": [_middle("SV020", 96, 1.24), _middle("SV026", 71, 2.1)],
            "diversity": Diversity(hhi_major=0.2, hhi_middle=0.1, effective_categories=10.0),
            "restaurant_density": RestaurantDensity(
                value=212.0, unit="stores_per_km2", store_count=167
            ),
            "lq_baseline": LqBaseline(requested_radius_m=2000),
            "citable": {"summary": False, "summary_text": False, "restaurant_density": False},
        }
    ).model_dump()


def _lifecycle(code: str, score: float, opened: int, closed: int) -> dict[str, Any]:
    return {
        "industry_id": code,
        "industry_name": lookup.get(code).name,
        "score": score,
        "type": "개업 우위" if opened > closed else "폐업 우위",
        "citable": {"type": False, "evidence": False},
        "confidence": "medium",
        "data_available": True,
        "score_available": True,
        "data_status": "observed",
        "data_complete": True,
        "metrics": {"period_open_count": opened, "period_close_count": closed},
        "evidence": [],
        "warning": None,
    }


def mock_business_lifecycle_data(*, with_supplement: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "summary": "목업 개폐업 자료입니다.",
        "metadata": {
            "area_code": "3110001",
            "area_name": "목업 상권",
            "base_quarter": "20262",
            "period": "최근 4분기",
            "quarter_count": 4,
        },
        "coverage": {"target_industries": 51, "scored_industries": 2, "unscored_industries": 49},
        "taxonomy": dict(TAXONOMY),
        "scoring_method": {},
        "industries": [_lifecycle("SV020", 72.0, 12, 9), _lifecycle("SV026", 28.0, 18, 16)],
    }
    if with_supplement:
        data["supplement_quarters"] = {
            "area_code": "3110001",
            "quarters": ["20253", "20254", "20261", "20262"],
            "count_unit": "개소",
            "rate_unit": "%",
            "industries": [
                {
                    "industry_id": "SV020",
                    "store_counts": [40, 41, 42, 42],
                    "opened_counts": [3, 3, 3, 3],
                    "closed_counts": [2, 2, 3, 2],
                    "close_rates": [5.0, 4.9, 7.1, 4.8],
                    "confidence": "medium",
                }
            ],
            "unsupported_industry_ids": [],
            "missing_industry_ids": [],
            "note": "목업 보완 자료입니다.",
            "retrieved_at": "2026-10-03T00:00:00+00:00",
        }
    return BusinessLifecycleData.model_validate(data).model_dump(exclude_unset=True)


def mock_floating_population_data() -> dict[str, Any]:
    raw = files("app.mock_data").joinpath("floating_population.json").read_text(encoding="utf-8")
    return FloatingPopulationData.model_validate(json.loads(raw)).model_dump(mode="json")


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
    return _analysis(task, "floating_population", mock_floating_population_data())


async def _business_lifecycle(task: AnalysisTask) -> AgentAnalysis:
    return _analysis(task, "business_lifecycle", mock_business_lifecycle_data())


async def _commercial_area(task: AnalysisTask) -> AgentAnalysis:
    return _analysis(task, "commercial_area", mock_commercial_area_data())


def mock_agents() -> dict[AgentId, Any]:
    """세 분석 에이전트를 모두 목업으로 채운 등록표입니다."""
    return {
        "floating_population": _floating_population,
        "business_lifecycle": _business_lifecycle,
        "commercial_area": _commercial_area,
    }


def _cited(payload: dict[str, Any], agent_id: str, code: str, leaf: str) -> dict[str, str]:
    for row in payload.get("industry_evidence", []):
        if row["agent_id"] == agent_id and row["industry_code"] == code:
            for path in row["paths"]:
                if path.endswith("/" + leaf):
                    return {"agent_id": agent_id, "path": path}
    for row in payload.get("industry_digest", []):
        for metric in row["metrics"] if row["code"] == code else []:
            if metric["agent_id"] == agent_id and metric["path"].endswith("/" + leaf):
                return {"agent_id": agent_id, "path": metric["path"]}
    builders = {
        "commercial_area": mock_commercial_area_data,
        "business_lifecycle": mock_business_lifecycle_data,
    }
    for record in scalar_records(builders[agent_id](), agent_id):
        if record["industry_code"] == code and record["path"].endswith("/" + leaf):
            return {"agent_id": agent_id, "path": record["path"]}
    raise KeyError(f"{agent_id}:{code}:{leaf}")


def mock_generate(system_prompt: str, input_json: str) -> dict[str, Any]:
    """중재 모델 호출 자리에 끼우는 고정 응답입니다."""
    payload = json.loads(input_json) if input_json.strip() else {}
    return {
        "status": "ok",
        "summary": "점심 수요가 기대되는 한식은 추천하고 이미 몰린 음료점은 피합니다.",
        "recommendations": [
            {
                "category": {"major": "음식점업", "middle": "한식 음식점"},
                "score": 72,
                "reasons": ["반경 안 한식 점포가 {0}개이고 주변보다 {1}배 몰려 있습니다."],
                "evidence": [
                    _cited(payload, "commercial_area", "SV020", "count"),
                    _cited(payload, "commercial_area", "SV020", "lq"),
                ],
                "risks": ["경쟁 점포가 {0}개라 가격 경쟁이 있습니다."],
            }
        ],
        "not_recommended": [
            {
                "category": {"major": "음식점업", "middle": "카페·비알코올 음료점"},
                "score": 28,
                "reasons": ["주변보다 {0}배 몰려 있고 개폐업 점수는 {1}점입니다."],
                "evidence": [
                    _cited(payload, "commercial_area", "SV026", "lq"),
                    _cited(payload, "business_lifecycle", "SV026", "score"),
                ],
                "risks": ["신규 진입 시 가격 경쟁에 노출됩니다."],
            }
        ],
        "limitations": ["목업 자료로 만든 결과입니다. 실제 판단에 쓰지 마세요."],
    }
