"""주소 근방을 카카오 지도에서 조회하는 도구

다른 세 분석 에이전트가 보는 자료는 전부 분기 단위 과거 통계임. 최종판단이 업종을
고르면서 "지금 실제로 어떤지" 확인할 자리가 없어서 이 도구를 둠.

상가업소 자료랑 세는 대상이 다른 게 핵심임. 강남역 반경 500m 기준으로 상가업소는
5,182곳인데 그중 경영컨설팅·회계·광고·법무가 1,800곳 넘음. 빌딩 안 사무실까지
사업자로 잡히기 때문임. 카카오는 지도에 등재된, 손님이 찾아갈 수 있는 곳만 셈.
"""

from .agent import CATEGORY_CODES, search
from .client import MapApiError, PlaceClient
from .config import Settings
from .schemas import Nearest, QueryResult, SearchResult

__all__ = [
    "CATEGORY_CODES",
    "MapApiError",
    "Nearest",
    "PlaceClient",
    "QueryResult",
    "SearchResult",
    "Settings",
    "search",
]
