from dataclasses import replace

from app.infrastructure.clients.education_zone import EducationZoneSettings, find_education_zones
from app.infrastructure.market_data.map_analysis.client import PlaceClient
from app.infrastructure.market_data.map_analysis.config import Settings


class PlaceServices:
    @staticmethod
    def place_search() -> PlaceClient:
        return PlaceClient(replace(Settings.from_env(), max_retries=0))

    @staticmethod
    async def education_zones(latitude, longitude, *, retry=True, **kwargs):
        if not retry:
            kwargs["settings"] = replace(EducationZoneSettings.from_env(), max_retries=0)
        return await find_education_zones(latitude, longitude, **kwargs)
