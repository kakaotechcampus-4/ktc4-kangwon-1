"""상가 정보 확인 화면이 쓰는 건축물대장 조회 API입니다."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.deps import current_user
from app.application.analysis import is_mock
from app.application.building import BuildingLookupFailed, lookup
from app.domain.building import BuildingRegistry

router = APIRouter(prefix="/api/v1", tags=["building"])
FAILURE_STATUS = {
    "invalid_address": 400,
    "outside_seoul": 422,
    "address_service": 502,
    "rate_limit": 429,
    "timeout": 504,
    "auth": 502,
    "upstream": 502,
}


@router.get(
    "/building-registry",
    response_model=BuildingRegistry,
    summary="주소로 건축물대장 표제부·층별개요·호실·오수정화시설을 조회합니다",
    # 외부 건축HUB API를 대리 호출합니다. 열어 두면 주소만 아는 사람이
    # 우리 쪽 할당량을 소진시킬 수 있어 로그인을 요구합니다(RATE_LIMIT -> 429 매핑 참고).
    dependencies=[Depends(current_user)],
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
    try:
        return await lookup(address, mock=is_mock(mock))
    except BuildingLookupFailed as exc:
        raise HTTPException(FAILURE_STATUS[exc.reason], exc.message) from exc.__cause__
