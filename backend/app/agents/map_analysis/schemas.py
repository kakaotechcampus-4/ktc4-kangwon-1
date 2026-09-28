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

    # API 검색 결과 건수이며 실제 영업 점포 전수가 아닙니다.
    count: int = Field(ge=0)

    # count 를 얼마나 믿을지 판단하라고 같이 주는 값
    #
    # 카카오 키워드 검색은 "치킨집"이 아니라 "치킨과 연관된 곳"을 줌. 역삼에서 "치킨"으로
    # 물었더니 68곳이 나왔는데 최근접이 샌드위치·인도음식·햄버거였음. count 자체를 고칠
    # 방법이 없어서(45건 상한 때문에 전수를 못 셈) 대신 표본에서 실제로 분류가 맞은
    # 건수를 같이 냄. matched 가 sampled 에 비해 적으면 count 를 조심해서 써야 함.
    sampled: int = Field(default=0, ge=0)
    matched: int = Field(default=0, ge=0)

    # 분류가 맞은 것 중에서만 고름. 0건이면 아예 안 실음 —
    # null 두면 읽는 쪽이 매번 분기해야 함
    nearest: Nearest | None = None
    # 역시 분류가 맞은 표본에서만 셈. 표본 기반이라 count 와 달리 전수 아님
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
