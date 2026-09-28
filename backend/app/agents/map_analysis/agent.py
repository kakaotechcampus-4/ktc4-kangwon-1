"""검색어 여러 개를 한 번에 조회해서 결과로 조립함

부르는 쪽(최종판단)은 업종 후보를 막 정한 참이라 한 번에 여러 개를 묻는다.
그래서 검색어를 리스트로 받고 카카오 요청은 동시에 던짐. 하나씩 받으면
모델 왕복이 검색어 수만큼 늘어나는데 그게 제일 비쌈.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date
from typing import Any

from app.schemas import DEFAULT_RADIUS_M, Site

from .client import MapApiError, PlaceClient
from .config import Settings
from .schemas import Nearest, QueryResult, SearchResult

# 카카오가 정한 18종 분류. 이름은 응답의 category_group_name 을 그대로 옮김
#
# 이 목록에 걸리는 말은 키워드 검색을 쓰면 안 됨. 실측에서 지하철역이 키워드 14 vs
# 카테고리 2, 학교가 6 vs 1 로 몇 배씩 부풀고, 대형마트는 키워드로 0이 나옴
# (상호명에 그 말이 든 가게까지 같이 걸리기 때문).
CATEGORY_CODES: dict[str, str] = {
    "대형마트": "MT1",
    "편의점": "CS2",
    "어린이집,유치원": "PS3",
    "학교": "SC4",
    "학원": "AC5",
    "주차장": "PK6",
    "주유소,충전소": "OL7",
    "지하철역": "SW8",
    "은행": "BK9",
    "문화시설": "CT1",
    "중개업소": "AG2",
    "공공기관": "PO3",
    "관광명소": "AT4",
    "숙박": "AD5",
    "음식점": "FD6",
    "카페": "CE7",
    "병원": "HP8",
    "약국": "PM9",
}

# 부르는 쪽이 공식 이름을 그대로 쓸 거라고 기대하면 안 됨. 쉼표로 묶인 둘은 따로 부름
CATEGORY_ALIASES: dict[str, str] = {
    "어린이집": "PS3",
    "유치원": "PS3",
    # 학교급을 빼놨더니 "초등학교"가 키워드로 새서, 반경 안에 학교가 0곳인데
    # 도시락집을 1곳 물어왔음. 교육환경보호구역 판단에 그대로 쓰이면 거짓말이 됨
    "초등학교": "SC4",
    "중학교": "SC4",
    "고등학교": "SC4",
    "대학교": "SC4",
    "대학": "SC4",
    "주유소": "OL7",
    "충전소": "OL7",
    "지하철": "SW8",
    "마트": "MT1",
}

__all__ = ["CATEGORY_CODES", "search"]


def _category_code(query: str) -> str | None:
    """18종 분류에 해당하는 말이면 그 코드를, 아니면 None"""
    key = query.strip().replace(" ", "")
    return CATEGORY_CODES.get(key) or CATEGORY_ALIASES.get(key)


def _distance_m(document: dict[str, Any]) -> int | None:
    # 카카오는 distance 를 문자열("45")로 줌. 없거나 숫자가 아니면 최근접을 못 만듦
    raw = document.get("distance")
    if not isinstance(raw, (str, int, float)):
        return None
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _matched(documents: list[Any], query: str, *, by_category: bool) -> list[dict[str, Any]]:
    """검색어와 분류가 실제로 맞는 표본만 남김

    분류 조회는 카카오가 이미 그 분류로 걸러 준 결과라 전부 맞다고 봄.
    키워드 조회는 그렇지 않아서 category_name 에 검색어가 들어 있는지 확인함.
    """
    kept = [d for d in documents if isinstance(d, dict)]
    if by_category:
        return kept
    key = query.strip()
    return [d for d in kept if key in str(d.get("category_name") or "")]


def _nearest(documents: list[dict[str, Any]]) -> Nearest | None:
    """sort=distance 로 받으므로 맨 앞이 제일 가까운 곳"""
    for document in documents:
        name = str(document.get("place_name") or "").strip()
        distance = _distance_m(document)
        if not name or distance is None:
            continue
        url = str(document.get("place_url") or "").strip()
        return Nearest(name=name, distance_m=distance, place_url=url or None)
    return None


def _brands(documents: list[dict[str, Any]]) -> dict[str, int]:
    """category_name 끝자락에서 브랜드 이름을 셈

    "음식점 > 카페 > 커피전문점 > 스타벅스" 처럼 마지막 조각이 브랜드인 경우가 있음.
    그런데 "음식점 > 한식 > 순대" 의 순대는 브랜드가 아님. 둘을 가르려고
    **가게 이름이 그 조각으로 시작하는지**를 봄 — "스타벅스 강남점"은 걸리고
    "농민백암순대 강남직영점"은 안 걸림. 어림짐작이라 상호를 다르게 쓰는
    브랜드는 놓침.

    표본(sample_size)에서만 세므로 전수가 아님. count 와 달리 참고용임.
    """
    counts: dict[str, int] = {}
    for document in documents:
        parts = [p.strip() for p in str(document.get("category_name") or "").split(">")]
        name = str(document.get("place_name") or "").strip()
        if len(parts) < 3 or not parts[-1] or not name.startswith(parts[-1]):
            continue
        counts[parts[-1]] = counts.get(parts[-1], 0) + 1
    return counts


def _to_result(payload: dict[str, Any], query: str, *, by_category: bool) -> QueryResult:
    documents = payload["documents"]
    kept = _matched(documents, query, by_category=by_category)
    return QueryResult(
        count=payload["meta"]["total_count"],
        sampled=len(documents),
        matched=len(kept),
        nearest=_nearest(kept),
        brands=_brands(kept),
    )


async def search(
    site: Site,
    queries: Sequence[str],
    *,
    radius_m: int = DEFAULT_RADIUS_M,
    settings: Settings | None = None,
    client: PlaceClient | None = None,
) -> SearchResult:
    """좌표 반경 안에서 검색어별 개수·최근접·브랜드를 찾아 돌려줌"""
    settings = settings or Settings.from_env()
    # 같은 말을 두 번 물어도 요청을 두 번 보내지 않음. 순서는 부른 쪽 그대로 유지
    wanted = list(dict.fromkeys(q.strip() for q in queries if q and q.strip()))
    if not wanted:
        raise ValueError("검색어가 비어 있습니다.")

    owns_client = client is None
    place_client = client or PlaceClient(settings)

    async def one(query: str) -> QueryResult:
        try:
            code = _category_code(query)
            if code:
                payload = await place_client.search_category(
                    code, site.latitude, site.longitude, radius_m
                )
            else:
                payload = await place_client.search_keyword(
                    query, site.latitude, site.longitude, radius_m
                )
            return _to_result(payload, query, by_category=code is not None)
        except MapApiError as exc:
            # 검색어 하나가 죽어도 나머지는 살려 보냄. 하나 때문에 전체가 비면 도구로 못 씀
            return QueryResult(count=0, error=exc.code)

    try:
        results = await asyncio.gather(*(one(query) for query in wanted))
    finally:
        if owns_client:
            await place_client.aclose()

    return SearchResult(
        radius_m=radius_m,
        queried_at=date.today().isoformat(),
        results=dict(zip(wanted, results, strict=True)),
    )
