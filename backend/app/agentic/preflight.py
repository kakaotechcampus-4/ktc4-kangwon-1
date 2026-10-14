"""로컬 채점 전에 필수 시설·보호구역을 한 번 관측합니다."""

import csv
import json
from dataclasses import replace

import httpx

from app.agents.map_analysis.client import MapApiError
from app.canonical import canonical_hash
from app.clock import utc_now_iso
from app.concurrency import run_in_thread
from app.db.connection import connect
from app.education_zone import (
    EducationZoneError,
    EducationZoneSettings,
    find_education_zones,
)
from app.industries import DATA_DIR

from .contracts import MapSearchInput
from .map_regulation import check_regulation, map_search
from .sql_tool import error
from .tools import SharedTools

FACILITIES = ("HP8", "SC4", "CT1", "AT4", "SW8")


def facility_requests():
    with (DATA_DIR / "industry_profile.csv").open(encoding="utf-8-sig", newline="") as handle:
        profiles = list(csv.DictReader(handle))
    required = [row for row in profiles if row["required_facilities"]]
    codes = {code for row in required for code in row["required_facilities"].split(";")}
    radius = int(max((float(row["max_distance_m"]) for row in required), default=500))
    return [(code, radius) for code in FACILITIES if code in codes]


async def _education_lookup(latitude, longitude, **kwargs):
    return await find_education_zones(
        latitude,
        longitude,
        settings=replace(EducationZoneSettings.from_env(), max_retries=0),
        **kwargs,
    )


def _facility_places(scope, reply, category):
    places = {}
    with connect(scope.path) as db:
        for place in reply.data.places:
            row = db.execute(
                "SELECT value_json FROM facts WHERE fact_id=? AND request_id=? AND snapshot_id=?",
                (place.distance_fact_id, scope.request_id, scope.snapshot_id),
            ).fetchone()
            if row is None:
                raise ValueError("시설 거리 fact가 현재 요청에 없습니다.")
            places[place.place_id] = {
                "category_code": category if place.match_status == "category_match" else None,
                "distance_m": json.loads(row[0]),
            }
    return places


async def collect_preflight(scope, site, shared=None):
    shared = shared or SharedTools()
    shared.regulation_lookup = shared.regulation_lookup or _education_lookup
    queries, places, limitations = {}, {}, []
    for category, radius in await run_in_thread(facility_requests):
        input = MapSearchInput(facility_code=category, radius_m=radius)
        key = canonical_hash(input.model_dump(mode="json"))
        if key not in shared.map_cache:
            try:
                shared.map_cache[key] = await map_search(scope, site, input, shared)
            except (MapApiError, TimeoutError, httpx.TransportError):
                shared.map_cache[key] = error("MAP_UNAVAILABLE", "필수 시설을 확인하지 못했습니다.")
            shared.map_keys.add(key)
        reply = shared.map_cache[key]
        known = reply.status in {"ok", "partial"} and reply.data is not None
        queries[key] = {
            "request": input.model_dump(mode="json"),
            "status": "ok" if known else "error",
            "place_ids": [p.place_id for p in reply.data.places] if known else [],
        }
        if known:
            places.update(await run_in_thread(_facility_places, scope, reply, category))
            limitations.extend(reply.warnings)
        else:
            limitations.append(f"{category} 필수 시설 최근접 거리를 확인하지 못했습니다.")
    try:
        await check_regulation(scope, site, shared)
    except (EducationZoneError, TimeoutError, httpx.TransportError):
        shared.regulation_scan = {
            "status": "error",
            "queried_at": utc_now_iso(),
            "zones": [],
            "warnings": ["교육환경보호구역을 확인하지 못했습니다."],
        }
        await check_regulation(scope, site, shared)
    limitations.extend(shared.regulation.limitations)
    return {
        "facilities": {"data": {"queries": queries, "places": places}},
        "education_zones": shared.regulation_scan,
        "limitations": list(dict.fromkeys(limitations)),
    }, shared
