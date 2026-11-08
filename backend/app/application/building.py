from app.application.errors import ADDRESS_INPUT_ERRORS, AddressError
from app.application.ports.demo import demo
from app.application.ports.sites import BuildingRegistryError, sites
from app.domain.building import BuildingRegistry


class BuildingLookupFailed(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


async def lookup(address: str, *, mock: bool) -> BuildingRegistry:
    if mock:
        return demo().building()
    try:
        return await sites().building(address)
    except AddressError as exc:
        invalid = exc.code in ADDRESS_INPUT_ERRORS
        raise BuildingLookupFailed(
            "invalid_address" if invalid else "address_service",
            "주소를 확인해 주세요." if invalid else "주소 조회 서비스에 실패했습니다.",
        ) from exc
    except BuildingRegistryError as exc:
        if exc.code == "RATE_LIMIT":
            raise BuildingLookupFailed(
                "rate_limit", "건축물대장 조회 한도를 초과했습니다."
            ) from None
        if exc.code == "UPSTREAM_TIMEOUT":
            raise BuildingLookupFailed(
                "timeout", "건축물대장 조회가 오래 걸려 멈췄어요. 잠시 후 다시 시도해 주세요."
            ) from None
        if exc.code == "AUTH":
            raise BuildingLookupFailed(
                "auth", "건축물대장 인증키 또는 사용 권한을 확인해 주세요."
            ) from None
        raise BuildingLookupFailed("upstream", "건축물대장 조회에 실패했습니다.") from exc
