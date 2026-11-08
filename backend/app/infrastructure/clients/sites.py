from app.infrastructure.clients.address import resolve_site
from app.infrastructure.clients.building_registry import lookup_building


class PublicSites:
    @staticmethod
    async def resolve(address):
        return await resolve_site(address)

    @staticmethod
    async def building(address):
        return await lookup_building(address)
