"""지도·규제 원문을 읽기 도구로 감싸고 서버에서 fact를 등록합니다."""

import asyncio
import json
import os
import uuid
from dataclasses import replace

from app.agents.business_lifecycle.area_resolver import polygon_contains_point
from app.agents.map_analysis.agent import _distance_m
from app.agents.map_analysis.client import PlaceClient
from app.agents.map_analysis.config import Settings
from app.agents.map_analysis.matching import match_place
from app.db.connection import connect
from app.education_zone import find_education_zones
from app.geo import to_epsg5181
from app.industries.catalog import INDUSTRIES
from app.industries.lookup import industry_terms
from app.storage.raw import _json, _write

from .contracts import IndustryRestriction, MapPlace, MapResult, RegulationResult, ToolReply
from .registry import register_fact
from .scoring import regulation


def _place_facts(scope, response_id, documents):
    with connect(scope.path) as db:
        rows = db.execute(
            "SELECT r.raw_row_id,r.raw_json FROM raw_rows r "
            "JOIN raw_response_rows e USING(raw_row_id) WHERE e.response_id=?",
            (response_id,),
        ).fetchall()

        refs = {_json(json.loads(r[1])): r[0] for r in rows}
        facts = {}
        for doc in documents:
            fields = []
            for key, metric, unit, value in [
                ("place_name", "place_name", "이름", doc.get("place_name")),
                ("category_name", "kakao_category", "분류", doc.get("category_name")),
                ("distance", "distance_m", "m", _distance_m(doc)),
            ]:
                fields.append(
                    register_fact(
                        scope,
                        industry_code=None,
                        source="map",
                        metric=metric,
                        value=value,
                        unit=unit,
                        status="observed" if value is not None else "unknown",
                        row_ids=[refs[_json(doc)]],
                        field_pointer="/" + key,
                        period="지도 조회 시점",
                        connection=db,
                    )
                )
            facts[doc["id"]] = fields
    return facts


async def map_search(scope, site, input, shared):
    owned = shared.map_client is None
    client = shared.map_client or PlaceClient(replace(Settings.from_env(), max_retries=0))
    queries = (
        [input.facility_code]
        if input.facility_code
        else industry_terms(input.industry_code)["includes"]
    )
    places, more = {}, False
    warnings = [
        "첫 페이지 검색 표본이며 실제 경쟁점 전수가 아닙니다. 0건은 동종 가게 없음이 아닙니다."
    ]
    try:
        async with asyncio.timeout(15):
            for query in queries:
                if shared.map_http >= 20:
                    from .raw_query import error

                    return error("BUDGET_EXCEEDED", "지도 HTTP 20회 상한입니다.")
                # 재시도 없는 클라이언트에서 실패한 전송도 예약 횟수에 포함합니다.
                shared.map_http += 1
                response = (
                    await client.search_category(
                        query, site.latitude, site.longitude, input.radius_m
                    )
                    if input.facility_code
                    else await client.search_keyword(
                        query, site.latitude, site.longitude, input.radius_m
                    )
                )
                documents = [
                    d
                    for d in response["documents"]
                    if isinstance(d, dict)
                    and isinstance(d.get("id"), str)
                    and d["id"].strip()
                    and isinstance(d.get("place_name"), str)
                    and d["place_name"].strip()
                    and isinstance(d.get("category_name", ""), str)
                ]
                response_id = await scope.record(
                    source="map",
                    source_type="api",
                    args={
                        "query": query,
                        "radius_m": input.radius_m,
                        "latitude": site.latitude,
                        "longitude": site.longitude,
                    },
                    page="1",
                    status=200,
                    payload=response,
                    secrets=[os.getenv("GEOCODING_API_KEY", "")],
                )
                facts = await _write(_place_facts, scope, response_id, documents)
                more = more or response["meta"].get("is_end") is not True
                for doc in documents:
                    status, rule = match_place(
                        input.industry_code,
                        doc["place_name"],
                        doc.get("category_name") or "",
                        doc.get("category_group_code"),
                        input.facility_code,
                    )
                    previous = places.get(doc["id"])
                    if previous and (previous.name, previous.kakao_category) != (
                        doc["place_name"],
                        doc.get("category_name") or "분류 미제공",
                    ):
                        status, rule = "unknown", None
                        warnings.append(
                            "같은 장소의 이름·분류가 상충하여 일치 여부를 미확인으로 남겼습니다."
                        )
                    places[doc["id"]] = MapPlace(
                        place_id=doc["id"],
                        name=doc["place_name"],
                        kakao_category=doc.get("category_name") or "분류 미제공",
                        distance_fact_id=facts[doc["id"]][2],
                        match_status=status,
                        match_rule_id=rule,
                        fact_ids=facts[doc["id"]],
                    )
    finally:
        if owned:
            await client.aclose()
    selected = list(places.values())[: input.limit]
    truncated = len(places) > input.limit
    return ToolReply(
        status="partial" if more or truncated else "ok",
        data=MapResult(
            observation_id="map_" + str(uuid.uuid4()),
            places=selected,
            coverage=1.0 if not more and not truncated else 0.0,
            has_more=more or truncated,
        ),
        fact_ids=[f for p in selected for f in p.fact_ids],
        warnings=warnings,
        truncated=truncated,
    )


def _regulation(scope, site, scan):
    raw = scan.model_dump(mode="json") if hasattr(scan, "model_dump") else scan
    if "center" in raw and raw["center"] != {
        "latitude": site.latitude,
        "longitude": site.longitude,
    }:
        raise ValueError("규제 좌표가 현재 요청과 다릅니다.")
    zones = raw.get("zones", [])
    contained = []
    verified = raw.get("status") == "ok"
    for zone in zones:
        geometry = zone.get("geometry")
        try:
            if not geometry:
                verified = False
            else:
                if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
                    raise ValueError("다각형 구역이 아닙니다.")
                polygons = (
                    [geometry["coordinates"]]
                    if geometry["type"] == "Polygon"
                    else geometry["coordinates"]
                )
                if not polygons or any(not rings for rings in polygons):
                    raise ValueError("빈 다각형입니다.")
                projected = [
                    [[to_epsg5181(p[1], p[0]) for p in ring] for ring in rings]
                    for rings in polygons
                ]
                x, y = to_epsg5181(site.latitude, site.longitude)
                if any(polygon_contains_point(rings, x, y) for rings in projected):
                    contained.append(zone)
        except (ValueError, TypeError, IndexError, KeyError, OverflowError):
            verified = False
    effective = raw | {"zones": contained if verified else zones, "contains_verified": verified}
    response = scope.record_sync(
        source="regulation",
        source_type="api",
        args={"latitude": site.latitude, "longitude": site.longitude},
        page="1",
        status=200 if raw["status"] == "ok" else 502,
        payload={"rows": [raw]},
        secrets=[os.getenv("VWORLD_API_KEY", "")],
    )
    with connect(scope.path) as db:
        ref = db.execute(
            "SELECT raw_row_id FROM raw_response_rows WHERE response_id=?", (response,)
        ).fetchone()[0]
    fact = register_fact(
        scope,
        industry_code=None,
        source="regulation",
        metric="zone_contains",
        value=bool(contained) if verified else None,
        unit="포함 여부",
        status="observed" if verified else "unknown",
        row_ids=[ref],
        period=raw["queried_at"],
    )
    restrictions = [
        IndustryRestriction(
            industry_code=code,
            status=regulation(code, effective),
            scope="whole"
            if code in {"I101", "I102"}
            else "partial"
            if code in {"R104", "I211"}
            else "none",
            fact_ids=[fact],
        )
        for code in INDUSTRIES
    ]
    return RegulationResult(
        status=raw["status"],
        queried_at=raw["queried_at"],
        contains_verified=verified,
        zones=zones,
        fact_ids=[fact],
        industry_restrictions=restrictions,
        limitations=raw.get("warnings", [])
        + ([] if verified else ["보호구역 좌표 포함 여부를 확인하지 못했습니다."])
        + ["건축물 용도는 확인하지 않았습니다."],
    )


def _stored_regulation(scope):
    with connect(scope.path) as db:
        rows = db.execute(
            "SELECT r.raw_json FROM raw_rows r JOIN raw_response_rows e USING(raw_row_id) "
            "JOIN raw_responses p USING(response_id) "
            "WHERE p.request_id=? AND p.snapshot_id=? AND p.source='regulation' "
            "ORDER BY p.collected_at DESC LIMIT 1",
            (scope.request_id, scope.snapshot_id),
        ).fetchall()
    if rows:
        raw = json.loads(rows[0][0])
        if raw.get("status") in {"ok", "error"} and "queried_at" in raw:
            return raw
    return None


async def check_regulation(scope, site, shared):
    if shared.regulation is None:
        scan = shared.regulation_scan
        if scan is None:
            scan = await _write(_stored_regulation, scope)
        if scan is None:
            lookup = shared.regulation_lookup or find_education_zones
            scan = await lookup(site.latitude, site.longitude, with_geometry=True)
        shared.regulation = await _write(_regulation, scope, site, scan)
    return shared.regulation
