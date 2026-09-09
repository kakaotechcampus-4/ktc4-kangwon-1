"""주소를 좌표로 바꿉니다. app/address.py가 완성되면 이 파일은 지웁니다."""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from .config import KAKAO_ADDRESS_URL, KAKAO_KEYWORD_URL, NOMINATIM_URL, Settings

USER_AGENT = "commercial-area-agent/1.0"
DETAIL_PATTERN = re.compile(r"\s*(?:지하\s*)?[\dA-Za-z]+(?:-\d+)?\s*(?:호|층|동)(?:\s|$).*$")
ROAD_BASE_PATTERN = re.compile(r"^(.*?(?:로|길)\s*\d+(?:-\d+)?)")


def split_detail(address: str) -> tuple[str, str | None]:
    base = DETAIL_PATTERN.sub("", address).strip(" ,")
    if not base or base == address.strip():
        return address.strip(), None
    detail = address.strip()[len(base) :].strip(" ,")
    return base, detail or None


def query_candidates(address: str) -> list[str]:
    cleaned = address.strip()
    candidates = [cleaned]
    base, _ = split_detail(cleaned)
    if base and base not in candidates:
        candidates.append(base)
    road = ROAD_BASE_PATTERN.match(cleaned)
    if road:
        road_only = road.group(1).strip()
        if road_only and road_only not in candidates:
            candidates.append(road_only)
    return candidates


class GeocodeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class GeocodeResult:
    query: str
    latitude: float
    longitude: float
    road_address: str | None
    jibun_address: str | None
    detail_address: str | None
    matched_query: str
    provider: str
    confidence: str


def _kakao(address: str, settings: Settings) -> GeocodeResult | None:
    headers = {"Authorization": f"KakaoAK {settings.geocoding_api_key}"}
    with httpx.Client(timeout=settings.request_timeout_s) as client:
        for url, kind in ((KAKAO_ADDRESS_URL, "address"), (KAKAO_KEYWORD_URL, "keyword")):
            response = client.get(url, headers=headers, params={"query": address, "size": 1})
            if response.status_code in {401, 403}:
                raise GeocodeError("KAKAO_AUTH", "카카오 REST 키가 거부됐습니다.")
            response.raise_for_status()
            documents = response.json().get("documents") or []
            if not documents:
                continue
            doc = documents[0]
            road = (doc.get("road_address") or {}).get("address_name") or doc.get("road_address_name")
            jibun = (doc.get("address") or {}).get("address_name") or doc.get("address_name")
            return GeocodeResult(
                query=address,
                latitude=float(doc["y"]),
                longitude=float(doc["x"]),
                road_address=road or None,
                jibun_address=jibun or None,
                detail_address=None,
                matched_query=address,
                provider="kakao",
                confidence="high" if kind == "address" else "medium",
            )
    return None


def _nominatim(address: str, settings: Settings) -> GeocodeResult | None:
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "ko"}
    params = {"q": address, "format": "json", "limit": 1, "countrycodes": "kr"}
    with httpx.Client(timeout=settings.request_timeout_s) as client:
        response = client.get(NOMINATIM_URL, headers=headers, params=params)
        response.raise_for_status()
        results = response.json()
    if not results:
        return None
    hit = results[0]
    return GeocodeResult(
        query=address,
        latitude=float(hit["lat"]),
        longitude=float(hit["lon"]),
        road_address=hit.get("display_name"),
        jibun_address=None,
        detail_address=None,
        matched_query=address,
        provider="nominatim",
        confidence="low",
    )


def geocode(address: str, settings: Settings) -> GeocodeResult:
    cleaned = (address or "").strip()
    if not cleaned:
        raise GeocodeError("EMPTY_ADDRESS", "주소가 비어 있습니다.")

    provider = (settings.geocoder or "auto").strip().lower()
    if provider == "auto":
        provider = "kakao" if settings.geocoding_api_key else "nominatim"

    if provider == "kakao" and not settings.geocoding_api_key:
        raise GeocodeError("NO_GEOCODING_KEY", "GEOCODING_API_KEY가 설정되지 않았습니다.")
    if provider not in {"kakao", "nominatim"}:
        raise GeocodeError("UNKNOWN_PROVIDER", f"지원하지 않는 지오코더입니다: {provider}")

    _, detail = split_detail(cleaned)
    lookup = _kakao if provider == "kakao" else _nominatim

    result = None
    for index, candidate in enumerate(query_candidates(cleaned)):
        try:
            found = lookup(candidate, settings)
        except httpx.HTTPError as exc:
            raise GeocodeError("UPSTREAM_FAILED", f"{type(exc).__name__}") from exc
        if found is not None:
            confidence = found.confidence
            if index > 0 and confidence == "high":
                confidence = "medium"
            result = GeocodeResult(
                query=cleaned,
                latitude=found.latitude,
                longitude=found.longitude,
                road_address=found.road_address,
                jibun_address=found.jibun_address,
                detail_address=detail,
                matched_query=candidate,
                provider=found.provider,
                confidence=confidence,
            )
            break

    if result is None:
        raise GeocodeError("NOT_FOUND", f"주소를 찾지 못했습니다: {cleaned}")
    return result
