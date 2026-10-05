"""검색어 여러 개를 한 번에 조회해서 결과로 조립함

부르는 쪽(최종판단)은 업종 후보를 막 정한 참이라 한 번에 여러 개를 묻는다.
그래서 검색어를 리스트로 받고 카카오 요청은 동시에 던짐. 하나씩 받으면
모델 왕복이 검색어 수만큼 늘어나는데 그게 제일 비쌈.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.industries.catalog import CATALOG_VERSION
from app.industries.lookup import get
from app.llm.budget import BudgetStorageError
from app.schemas import (
    AnalysisTask,
    MapData,
    MapIndustry,
    MapLookupPlan,
    MapObservation,
    MapPlace,
    MapQueryResult,
)

from .client import MapApiError, PlaceClient
from .config import Settings
from .mapping import GenerateMapping, map_categories

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

__all__ = ["CATEGORY_CODES", "CATEGORY_ALIASES", "observe"]


def category_code(query: str) -> str | None:
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
    except (TypeError, ValueError, OverflowError):
        return None
    return value if value >= 0 else None


def failed_observation(task: AnalysisTask, plan: MapLookupPlan, code: str) -> MapObservation:
    """외부 실패를 검색 0건과 구분합니다."""
    return MapObservation(
        request_id=task.request_id,
        observation_id=uuid.uuid4().hex,
        site=task.site,
        radius_m=task.radius_m,
        queried_at=datetime.now(UTC).isoformat(),
        master_version=CATALOG_VERSION,
        status="error",
        warnings=["지도 조회 실패"],
        data=MapData(
            queries={
                f"q{i}": MapQueryResult(
                    request=q,
                    status="error",
                    method="category" if q.facility_code else "keyword",
                    category_code=q.facility_code,
                    error=code,
                )
                for i, q in enumerate(plan.unique_queries(), 1)
            }
        ),
    )


async def observe(
    task: AnalysisTask,
    plan: MapLookupPlan,
    *,
    settings: Settings | None = None,
    client: PlaceClient | None = None,
    generate_mapping: GenerateMapping | None = None,
    mapping_cache_path: Path | None = None,
) -> MapObservation:
    """원본 장소를 보존하고 조회 표본만 공통 업종으로 집계합니다."""
    task, plan = AnalysisTask.model_validate(task), MapLookupPlan.model_validate(plan)
    place_client = client or PlaceClient(settings or Settings.from_env())
    wanted = plan.unique_queries()

    def category(q):
        if q.facility_code:
            return q.facility_code
        # 카카오 대응이 명확한 음식점·카페만 제한합니다. 다른 업종은 임의 배정하지 않습니다.
        if q.industry_code == "SV026":
            return "CE7"
        return "FD6" if get(q.industry_code).major_code == "I2" else None

    async def one(q):
        try:
            if q.facility_code:
                return await place_client.search_category(
                    q.facility_code, task.site.latitude, task.site.longitude, task.radius_m
                )
            return await place_client.search_keyword(
                q.query,
                task.site.latitude,
                task.site.longitude,
                task.radius_m,
                category_group_code=category(q),
            )
        except MapApiError as exc:
            return exc.code

    try:
        responses = await asyncio.gather(*(one(q) for q in wanted))
    finally:
        if client is None:
            await place_client.aclose()
    queries: dict[str, MapQueryResult] = {}
    places: dict[str, MapPlace] = {}
    industry_ids: set[str] = set()
    conflicts: set[str] = set()
    warnings = ["지도 등록 정보의 첫 페이지 표본이며 실제 영업 점포 전수가 아닙니다."]
    degraded = False
    for i, (q, response) in enumerate(zip(wanted, responses, strict=True), 1):
        base: dict[str, Any] = dict(
            request=q,
            method="category" if q.facility_code else "keyword",
            category_code=q.facility_code,
        )
        if isinstance(response, str):
            queries[f"q{i}"] = MapQueryResult(**base, status="error", error=response)
            continue
        ids = []
        for document in response["documents"]:
            if (
                not isinstance(document, dict)
                or not isinstance(document.get("id"), str)
                or not document["id"].strip()
                or not str(document.get("place_name") or "").strip()
            ):
                degraded = True
                continue
            pid = document["id"]
            try:
                place = MapPlace(
                    name=document["place_name"],
                    category_name=document.get("category_name") or "",
                    category_code=document.get("category_group_code") or "",
                    distance_m=_distance_m(document),
                    place_url=document.get("place_url") or None,
                )
            except ValidationError:
                degraded = True
                continue
            if pid in places and (places[pid].category_name, places[pid].category_code) != (
                place.category_name,
                place.category_code,
            ):
                conflicts.add(pid)
            else:
                places[pid] = place
            if pid not in ids:
                ids.append(pid)
            if q.kind == "industry":
                industry_ids.add(pid)
        is_end = response["meta"].get("is_end")
        queries[f"q{i}"] = MapQueryResult(
            **base,
            status="ok",
            total_count=response["meta"]["total_count"],
            place_ids=ids,
            has_more=not is_end if type(is_end) is bool else None,
        )
    if degraded:
        warnings.append("형식이 잘못된 장소를 제외하고 유효한 장소만 보존했습니다.")
    categories = {}
    category_ids: dict[tuple[str, str], str] = {}
    for pid in sorted(industry_ids - conflicts):
        p = places[pid]
        if not p.category_name.strip() and not p.category_code.strip():
            continue
        key = (p.category_name, p.category_code)
        if key not in category_ids:
            cid = f"c{len(category_ids) + 1}"
            category_ids[key] = cid
            categories[cid] = {"name": p.category_name, "code": p.category_code}
    try:
        mappings = await map_categories(
            categories, generate=generate_mapping, cache_path=mapping_cache_path
        )
    except BudgetStorageError:
        raise
    except (RuntimeError, ValueError):
        mappings = {}
        degraded = True
        warnings.append("업종 매핑 실패: 원본 장소만 보존했습니다.")
    for pid in industry_ids:
        p = places[pid]
        mapping = mappings.get(category_ids.get((p.category_name, p.category_code), ""))
        changes: dict[str, Any]
        if pid in conflicts:
            changes = dict(mapping_status="ambiguous", reason="원본 분류 충돌")
        elif mapping is None:
            changes = dict(mapping_status="unmapped", reason="매핑 결과 없음")
        else:
            changes = dict(
                mapping_status=mapping.status,
                industry_code=mapping.industry_code,
                mapping_method="llm",
                reason=mapping.reason,
            )
        places[pid] = MapPlace.model_validate({**p.model_dump(), **changes})
        degraded |= places[pid].mapping_status != "mapped"
    unmapped_count = sum(places[pid].mapping_status != "mapped" for pid in industry_ids)
    if unmapped_count:
        warnings.append(
            f"업종 미확정 장소 {unmapped_count}곳은 원본만 보존하고 업종별 건수에서 제외했습니다."
        )
    groups: dict[str, list[str]] = {}
    for pid, p in places.items():
        if p.industry_code:
            groups.setdefault(p.industry_code, []).append(pid)
    industries = {
        code: MapIndustry(
            name=get(code).name,
            major=get(code).major_name,
            place_ids=sorted(ids),
            sampled_count=len(ids),
        )
        for code, ids in groups.items()
    }
    successes = [q for q in queries.values() if q.status == "ok"]
    status = (
        "error"
        if not successes
        else "partial"
        if len(successes) != len(queries) or degraded
        else "no_data"
        if all(q.total_count == 0 for q in successes)
        else "ok"
    )
    return MapObservation.model_validate(
        dict(
            request_id=task.request_id,
            observation_id=uuid.uuid4().hex,
            site=task.site,
            radius_m=task.radius_m,
            queried_at=datetime.now(UTC).isoformat(),
            master_version=CATALOG_VERSION,
            status=status,
            data=MapData(queries=queries, places=places, industries=industries),
            warnings=warnings,
        )
    )
