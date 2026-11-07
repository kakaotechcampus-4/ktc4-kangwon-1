import os
from dataclasses import replace

from app.infrastructure.clients.education_zone import EducationZoneSettings, find_education_zones
from app.infrastructure.market_data.map_analysis.client import PlaceClient
from app.infrastructure.market_data.map_analysis.config import Settings


class PlaceServices:
    @staticmethod
    def place_search() -> PlaceClient:
        return PlaceClient(replace(Settings.from_env(), max_retries=0))

    @staticmethod
    def map_secrets():
        return [os.getenv("GEOCODING_API_KEY", "")]

    @staticmethod
    def zone_secrets():
        return [os.getenv("VWORLD_API_KEY", "")]

    @staticmethod
    async def education_zones(latitude, longitude, *, retry=True, **kwargs):
        if retry:
            return await find_education_zones(latitude, longitude, **kwargs)
        settings = replace(EducationZoneSettings.from_env(), max_retries=0)
        return await find_education_zones(latitude, longitude, settings=settings, **kwargs)
