"""서비스와 그래프에서 조건과 문구가 같은 구성 검사만 공유합니다."""

from app.schemas import AGENT_IDS, EVALUATOR_IDS


def validate_address(address):
    if not isinstance(address, str) or not address.strip():
        raise ValueError("주소가 비어 있습니다.")


def validate_request_id(request_id):
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("요청 ID가 비어 있습니다.")


def validate_agents(agents):
    if set(agents) != set(AGENT_IDS) or not all(callable(a) for a in agents.values()):
        raise ValueError("세 분석 에이전트의 호출 함수를 등록해 주세요.")


def validate_map_lookup(map_lookup):
    if map_lookup is not None and not callable(map_lookup):
        raise ValueError("지도 조회 함수가 필요합니다.")


def validate_allow_questions(allow_questions):
    if type(allow_questions) is not bool:
        raise ValueError("질문 허용 여부는 참 또는 거짓이어야 합니다.")


def validate_evaluators(generators):
    if (
        not generators
        or set(generators) != set(EVALUATOR_IDS)
        or not all(callable(fn) for fn in generators.values())
    ):
        raise ValueError("평가자 네 명의 호출 함수를 등록해 주세요.")


def validate_specialists(generators, *, with_map):
    if (
        not generators
        or not set(AGENT_IDS) <= set(generators)
        or (with_map and "map_analysis" not in generators)
        or not all(callable(fn) for fn in generators.values())
    ):
        raise ValueError("전문가 호출 함수를 등록해 주세요.")
