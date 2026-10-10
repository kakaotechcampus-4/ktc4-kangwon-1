from collections.abc import Iterator, Mapping
from typing import Any, Final

from pydantic import BaseModel

from app.agents.business_lifecycle.schemas import BusinessLifecycleData
from app.agents.commercial_area.schemas import CommercialAreaData
from app.agents.floating_population.schemas import FloatingPopulationData
from app.schemas import IndustryRow, MapData, Schema

DATA_MODELS: Final[dict[str, type[Schema]]] = {
    "business_lifecycle": BusinessLifecycleData,
    "commercial_area": CommercialAreaData,
    "floating_population": FloatingPopulationData,
    "map_analysis": MapData,
}
WITHOUT_INDUSTRY_ROWS: Final = frozenset({"floating_population"})


def parse_data(agent_id: str, data: Mapping[str, Any]) -> Schema:
    return DATA_MODELS[agent_id].model_validate(data)


def industry_owners(agent_id: str, data: Mapping[str, Any]) -> dict[str, str]:
    if agent_id in WITHOUT_INDUSTRY_ROWS or not data:
        return {}
    model = parse_data(agent_id, data)
    if isinstance(model, MapData):
        return _map_owners(model)
    return dict(_rows(model, ""))


def _escape(key: object) -> str:
    return str(key).replace("~", "~0").replace("/", "~1")


def _rows(value: Any, path: str) -> Iterator[tuple[str, str]]:
    if isinstance(value, IndustryRow):
        yield path, value.owner_code
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _rows(getattr(value, name), f"{path}/{_escape(name)}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _rows(item, f"{path}/{index}")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _rows(item, f"{path}/{_escape(key)}")


def _map_owners(data: MapData) -> dict[str, str]:
    owners = {f"/industries/{_escape(code)}": code for code in data.industries}
    owners.update(
        {
            f"/places/{_escape(place_id)}": place.industry_code
            for place_id, place in data.places.items()
            if place.mapping_status == "mapped" and place.industry_code
        }
    )
    return owners
