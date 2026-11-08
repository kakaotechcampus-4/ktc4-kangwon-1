from typing import Any, Protocol

from app.application.ports.slot import Slot
from app.domain.building import BuildingRegistry


class Demo(Protocol):
    def run_options(self, *, ask: bool) -> dict[str, Any]: ...
    def resume_options(self) -> dict[str, Any]: ...
    def building(self) -> BuildingRegistry: ...


demo: Slot[Demo] = Slot()
