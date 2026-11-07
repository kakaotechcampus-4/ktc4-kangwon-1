from typing import Any, Protocol

from app.application.ports.slot import Slot


class MapApiError(Exception):
    """카카오 조회 실패. 원문 예외 메시지는 안 담음 — 키가 섞여 나갈 수 있음"""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class EducationZoneError(Exception):
    """구역 조회 실패입니다. 키와 원문 응답은 메시지에 담지 않습니다."""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class PlaceSearch(Protocol):
    async def search_keyword(
        self,
        query: str,
        latitude: float,
        longitude: float,
        radius_m: int,
        *,
        category_group_code: str | None = None,
    ) -> dict[str, Any]: ...
    async def search_category(
        self, category_group_code: str, latitude: float, longitude: float, radius_m: int
    ) -> dict[str, Any]: ...
    async def aclose(self) -> None: ...


class Places(Protocol):
    def place_search(self) -> PlaceSearch: ...
    async def education_zones(
        self, latitude: float, longitude: float, *, retry: bool = True, **kwargs: Any
    ) -> Any: ...


places: Slot[Places] = Slot()
