"""분석·답변·재시도에 사용하는 외부 호출 없는 대역을 한 곳에서 구성합니다."""

from typing import Any, Literal

from app.mocks import (
    evaluator,
    interactive_decision,
    map_observation,
    mock_agents,
    mock_generate,
    mock_resolve,
    specialist,
    zone_scan,
)
from app.schemas import AGENT_IDS, EVALUATOR_IDS


def mock_dependencies(
    phase: Literal["analysis", "resume", "retry"],
    *,
    with_map: bool = False,
    allow_questions: bool = False,
    evaluators_enabled: bool = False,
) -> dict[str, Any]:
    dependencies: dict[str, Any] = {
        "generate": interactive_decision(with_map=with_map, allow_questions=allow_questions)
        if phase != "analysis" or with_map or allow_questions or evaluators_enabled
        else mock_generate,
        "generate_specialists": dict.fromkeys((*AGENT_IDS, "map_analysis"), specialist),
        "generate_evaluators": dict.fromkeys(EVALUATOR_IDS, evaluator),
        "map_lookup": map_observation if with_map or phase == "resume" else None,
        "find_zones": zone_scan,
        "supplements": [],
    }
    if phase == "retry":
        # 재시도는 저장된 자료만 쓰므로 지도·보완·전문가 도구를 받지 않습니다.
        return {key: dependencies[key] for key in ("generate", "generate_evaluators")}
    if phase == "analysis":
        dependencies.update(resolve=mock_resolve, agents=mock_agents())
    return dependencies
