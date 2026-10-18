"""상가 정보 확인 화면이 쓰는 건축물대장 조회 API입니다."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.address import GeocodeError
from app.building_registry import BuildingRegistry, BuildingRegistryError, lookup_building
from app.services.mock import building_registry as mock_building_registry

from .analyses import is_mock

router = APIRouter(prefix="/api/v1", tags=["building"])


@router.get(
    "/building-registry",
    response_model=BuildingRegistry,
    summary="주소로 건축물대장 표제부·층별개요·호실·오수정화시설을 조회합니다",
)
async def get_building_registry(
    address: str = Query(
        min_length=1,
        max_length=200,
        description="건물 주소. 층·호 같은 상세주소가 붙어 있어도 됩니다.",
        examples=["서울 송파구 위례광장로 199"],
    ),
    mock: bool = Query(
        default=False,
        description="외부 API 호출 없이 고정 응답을 돌려줍니다. 화면 연동용입니다.",
    ),
) -> BuildingRegistry:
    """조회 결과는 저장하지 않습니다. `MOCK_MODE` 환경변수가 켜져 있어도 고정 응답입니다."""
    if is_mock(mock):
        return mock_building_registry()
    try:
        return await lookup_building(address)
    except GeocodeError as exc:
        invalid = exc.code in {"EMPTY_ADDRESS", "NOT_FOUND", "ADDRESS_AMBIGUOUS"}
        raise HTTPException(
            400 if invalid else 502,
            "주소를 확인해 주세요." if invalid else "주소 조회 서비스에 실패했습니다.",
        ) from exc
    except BuildingRegistryError as exc:
        raise HTTPException(502, "건축물대장 조회에 실패했습니다.") from exc
