from typing import Protocol

from app.application.ports.slot import Slot
from app.domain.building import BuildingRegistry
from app.domain.schemas import Site


class BuildingRegistryError(Exception):
    """건축HUB 조회 실패입니다. 키와 원문 응답은 메시지에 담지 않습니다."""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class Sites(Protocol):
    async def resolve(self, address: str) -> Site: ...
    async def building(self, address: str) -> BuildingRegistry: ...


sites: Slot[Sites] = Slot()
