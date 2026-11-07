from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.application.ports.slot import Slot


@dataclass(frozen=True)
class CellRow:
    values: dict[str, Any]
    industry_code: str | None


class LocalData(Protocol):
    path: Path
    versions: list[dict[str, Any]]

    def analyze(self, task: Any) -> dict[str, Any]: ...
    def cell_row(self, source: str, version_id: str, row_key: str) -> CellRow | None: ...


class Market(Protocol):
    @property
    def reference_version(self) -> str: ...
    @property
    def source_names(self) -> Mapping[str, str]: ...

    def local_data(self, path: Path | None) -> LocalData: ...
    def format_snapshot(self, task: Any, scope: Any) -> tuple[dict, dict, list]: ...


market: Slot[Market] = Slot()
