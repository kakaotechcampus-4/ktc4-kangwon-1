from app.application.errors import ADDRESS_INPUT_ERRORS, AddressError
from app.infrastructure.clients.building_registry import (
    BuildingRegistry,
    BuildingRegistryError,
    lookup_building,
)
from app.infrastructure.mock import building_registry as mock_building_registry


class BuildingLookupFailed(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


async def lookup(address: str, *, mock: bool) -> BuildingRegistry:
    if mock:
        return mock_building_registry()
    try:
        return await lookup_building(address)
    except AddressError as exc:
        invalid = exc.code in ADDRESS_INPUT_ERRORS
        raise BuildingLookupFailed(
            400 if invalid else 502,
            "주소를 확인해 주세요." if invalid else "주소 조회 서비스에 실패했습니다.",
        ) from exc
    except BuildingRegistryError as exc:
        if exc.code == "RATE_LIMIT":
            raise BuildingLookupFailed(429, "건축물대장 조회 한도를 초과했습니다.") from None
        if exc.code == "UPSTREAM_TIMEOUT":
            raise BuildingLookupFailed(
                504, "건축물대장 조회가 오래 걸려 멈췄어요. 잠시 후 다시 시도해 주세요."
            ) from None
        if exc.code == "AUTH":
            raise BuildingLookupFailed(
                502, "건축물대장 인증키 또는 사용 권한을 확인해 주세요."
            ) from None
        raise BuildingLookupFailed(502, "건축물대장 조회에 실패했습니다.") from exc
