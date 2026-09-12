"""입력 주소를 정규화하고 좌표로 변환합니다.

좌표 변환 구현은 `app/agents/commercial_area/geocode.py`에 있고, 이 모듈은
팀 공통 진입점으로 그 결과를 `Site`로 바꿔 줍니다. 에이전트는 이 모듈만 씁니다.
"""

from __future__ import annotations

from app.agents.commercial_area.config import Settings
from app.agents.commercial_area.geocode import GeocodeError, geocode
from app.schemas import Site

__all__ = ["GeocodeError", "resolve_site"]


async def resolve_site(address: str, settings: Settings | None = None) -> Site:
    """주소 문자열을 좌표까지 채운 `Site`로 바꿉니다.

    좌표를 찾지 못하면 `GeocodeError`를 올립니다. 호출한 쪽이 사용자에게
    보여 줄 메시지를 정합니다.
    """
    settings = settings or Settings.from_env()
    found = await geocode(address, settings)
    return Site(
        input_address=address.strip(),
        road_address=found.road_address,
        jibun_address=found.jibun_address,
        detail_address=found.detail_address,
        latitude=found.latitude,
        longitude=found.longitude,
    )
