"""지도 전문가에게 검색 요약과 필요한 업종의 검증 경로만 제공합니다."""

from app.evidence import map_citations
from app.schemas import MapData, MapQueryResult


def query_summary(query: MapQueryResult) -> dict:
    return {
        "query": query.request.query,
        "industry_code": query.request.industry_code,
        **({"facility_code": query.request.facility_code} if query.request.facility_code else {}),
        "status": query.status,
        "total_count": query.total_count,
        "match_summary": {
            status: sum(match == status for match in query.matches.values())
            for status in ("same", "different", "unclear")
        },
    }


def selected_citations(data: MapData | dict, codes: set[str]) -> dict:
    return {code: rows for code, rows in map_citations(data).items() if code in codes}
