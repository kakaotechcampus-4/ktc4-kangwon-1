"""검증된 지도 모델의 동종 표본·시설 근거를 검사합니다."""

from app.schemas import MapData

from .pointer import escape_pointer, parse_pointer, resolve_pointer

MAP_AGENT_ID = "map_analysis"


def map_path_reason(path: str, code: str | None, data: MapData) -> str | None:
    try:
        parts = parse_pointer(path)
    except ValueError:
        return "형식"
    if len(parts) != 3:
        return "형식"
    section, key, field = parts
    if section not in {"industries", "places", "queries"}:
        return "구역"
    if key not in getattr(data, section):
        return "없음"
    if section == "industries":
        if field != "sampled_count":
            return "필드"
        return None if code == key else "업종"
    if section == "queries":
        query = data.queries[key]
        if field != "total_count" or (query.request.kind == "industry" and query.total_count != 0):
            return "필드"
        if query.status != "ok":
            return "없음"
        return (
            None
            if query.request.kind == "infrastructure"
            or (code is not None and query.request.industry_code == code)
            else "업종"
        )
    if field not in {"name", "distance_m"}:
        return "필드"
    place = data.places[key]
    if getattr(place, field) is None:
        return "없음"
    same = code in data.industries and key in data.industries[code].place_ids
    facility = place.mapping_status == "not_applicable" and any(
        query.status == "ok" and query.request.kind == "infrastructure" and key in query.place_ids
        for query in data.queries.values()
    )
    return None if same or facility else "업종"


def valid_map_path(path: str, code: str | None, data: MapData | dict) -> bool:
    """기존 dict 호출도 입구에서만 모델로 변환합니다."""
    return (
        map_path_reason(
            path,
            code,
            data if isinstance(data, MapData) else MapData.model_validate(data or {"queries": {}}),
        )
        is None
    )


def map_citations(data: MapData | dict) -> dict[str, list[dict]]:
    """검증된 경로만 업종별로 묶습니다. _facility는 시설 근거입니다."""
    if not data:
        return {}
    data = data if isinstance(data, MapData) else MapData.model_validate(data)
    queries, industries, places = data.queries, data.industries, data.places
    codes = dict.fromkeys(
        [
            *industries,
            *(q.request.industry_code for q in queries.values() if q.request.industry_code),
        ]
    )
    result = {}

    def pointer(section, key, field):
        return f"/{section}/{escape_pointer(key)}/{field}"

    for group in [*codes, "_facility"]:
        code = None if group == "_facility" else group
        paths = [pointer("industries", code, "sampled_count")] if code in industries else []
        relevant = {
            key: q
            for key, q in queries.items()
            if (q.request.industry_code == code if code else q.request.kind == "infrastructure")
        }
        paths.extend(pointer("queries", key, "total_count") for key in relevant)
        ids = (
            (industries[code].place_ids if code in industries else [])
            if code
            else {pid for q in relevant.values() for pid in q.place_ids}
        )
        nearest = sorted(
            (pid for pid in ids if pid in places),
            key=lambda pid: (
                places[pid].distance_m if places[pid].distance_m is not None else float("inf"),
                pid,
            ),
        )[:10]
        paths.extend(
            pointer("places", pid, field) for pid in nearest for field in ("name", "distance_m")
        )
        rows = [
            {"path": path, "value": resolve_pointer(data, path)}
            for path in paths
            if map_path_reason(path, code, data) is None
        ]
        if rows:
            result[group] = rows
    return result
