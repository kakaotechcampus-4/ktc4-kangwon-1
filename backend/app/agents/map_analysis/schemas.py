"""지도 조회가 돌려주는 자료 구조

호출자(최종판단)가 이 키를 그대로 읽음. 즉 **키 이름이 곧 계약임.**
바꿀 때는 도구 연결한 쪽이랑 같이 바꿔야 함.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas import RadiusMeters, Schema, Text


class Nearest(Schema):
    """반경 안에서 제일 가까운 한 곳"""

    name: Text
    # 카카오는 distance 를 문자열("40")로 줌. 여기서 정수 미터로 고정함
    distance_m: int = Field(ge=0)
    place_url: Text | None = None


class QueryResult(Schema):
    """검색어 하나에 대한 답"""

    # 반경 안 전체 개수. meta.total_count 라서 목록 상한(45건)이랑 무관하게 정확함
    count: int = Field(ge=0)
    # 0건이면 아예 안 실음. null 두면 읽는 쪽이 매번 분기해야 함
    nearest: Nearest | None = None
    # 표본(sample_size)에서만 뽑아서 밀집 지역에서는 일부만 잡힘. count 랑 달리 전수 아님
    brands: dict[Text, int] = Field(default_factory=dict)
    # 이 검색어만 실패했을 때 채움. 나머지 검색어 결과는 그대로 돌려줌
    error: Text | None = None


class SearchResult(Schema):
    """search() 한 번의 결과 전체"""

    radius_m: RadiusMeters
    # 살아 있는 API라 기준 기간이 없음. 언제 본 값인지만 남김
    queried_at: Text
    # 검색어를 그대로 키로 씀. 무슨 말로 물어서 이 숫자가 나왔는지 남아야 함
    results: dict[Text, QueryResult]
