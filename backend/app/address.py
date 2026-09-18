"""카카오 주소 검색의 단일 일치 후보만 공통 Site로 확정합니다."""

from __future__ import annotations

import math
import re
from typing import Any

import httpx

from app.config import AddressSettings
from app.schemas import Site

KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
BASE_PATTERN = re.compile(
    r"^(?P<region>.*?)[가-힣0-9·.]+(?:로|길|동|가|읍|면|리)"
    r"\s+(?:지하\s*|산\s*)?\d+(?:-\d+)?(?=$|[\s,(])"
)
REGION_ALIASES = {
    "서울특별시": "서울",
    "부산광역시": "부산",
    "대구광역시": "대구",
    "인천광역시": "인천",
    "광주광역시": "광주",
    "대전광역시": "대전",
    "울산광역시": "울산",
    "세종특별자치시": "세종",
    "경기도": "경기",
    "강원도": "강원",
    "강원특별자치도": "강원",
    "충청북도": "충북",
    "충청남도": "충남",
    "전라북도": "전북",
    "전북특별자치도": "전북",
    "전라남도": "전남",
    "경상북도": "경북",
    "경상남도": "경남",
    "제주도": "제주",
    "제주특별자치도": "제주",
}


class GeocodeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


def split_detail(address: str) -> tuple[str, str | None]:
    cleaned = address.strip()
    match = BASE_PATTERN.match(cleaned)
    if match is None:
        return cleaned, None
    return match.group(), cleaned[match.end() :].lstrip(" ,") or None


def _normalized(address: str) -> list[str]:
    tokens = address.split()
    if tokens:
        tokens[0] = REGION_ALIASES.get(tokens[0], tokens[0])
    return tokens


def _candidate(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("주소 응답 객체가 아닙니다.")
    meta, docs = payload.get("meta"), payload.get("documents")
    if not isinstance(meta, dict) or not isinstance(docs, list):
        raise ValueError("주소 응답 구조가 잘못되었습니다.")
    total, pageable, is_end = (meta.get(key) for key in ("total_count", "pageable_count", "is_end"))
    if (
        type(total) is not int
        or type(pageable) is not int
        or type(is_end) is not bool
        or total < 0
        or pageable < 0
    ):
        raise ValueError("주소 검색 메타데이터가 잘못되었습니다.")
    if total > 1 or pageable > 1 or not is_end or len(docs) > 1:
        raise GeocodeError(
            "ADDRESS_AMBIGUOUS", "주소 후보가 여러 개입니다. 전체 주소를 입력하세요."
        )
    if total == pageable == 0 and not docs:
        raise GeocodeError("NOT_FOUND", "주소를 찾지 못했습니다.")
    if total != 1 or pageable != 1 or len(docs) != 1 or not isinstance(docs[0], dict):
        raise ValueError("주소 후보 수가 일치하지 않습니다.")
    return docs[0]


def _base_name(doc: dict[str, Any], key: str) -> str | None:
    value = doc.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("기본 주소 구조가 잘못되었습니다.")
    name = value.get("address_name")
    if (
        not isinstance(name, str)
        or not name.strip()
        or BASE_PATTERN.fullmatch(name.strip()) is None
    ):
        raise ValueError("도로명 또는 지번 기본 주소가 없습니다.")
    return name.strip()


async def resolve_site(
    address: str,
    settings: AddressSettings | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> Site:
    cleaned = address.strip()
    if not cleaned:
        raise GeocodeError("EMPTY_ADDRESS", "주소가 비어 있습니다.")
    settings = settings or AddressSettings.from_env()
    if (
        not isinstance(settings.api_key, str)
        or not settings.api_key.strip()
        or type(settings.timeout) not in (float, int)
        or not math.isfinite(settings.timeout)
        or settings.timeout <= 0
    ):
        raise GeocodeError(
            "ADDRESS_CONFIG_ERROR", "카카오 REST 키와 주소 조회 제한시간을 확인하세요."
        )
    base, detail = split_detail(cleaned)
    normalized = _normalized(base)
    match = BASE_PATTERN.fullmatch(base)
    # ponytail: 생략 주소를 추측하지 않습니다. 필요하면 검증 가능한 별칭만 추가합니다.
    if (
        match is None
        or len(normalized) < 3
        or normalized[0] not in REGION_ALIASES.values()
        or any(
            re.fullmatch(r"[가-힣0-9·.]+(?:시|군|구|읍|면|동|가|리)", part) is None
            for part in match.group("region").split()[1:]
        )
    ):
        raise GeocodeError("ADDRESS_AMBIGUOUS", "시·도와 도로명 건물번호 또는 지번을 입력하세요.")
    if client is None:
        async with httpx.AsyncClient(timeout=settings.timeout) as owned:
            return await resolve_site(cleaned, settings, client=owned)
    try:
        response = await client.get(
            KAKAO_ADDRESS_URL,
            headers={"Authorization": f"KakaoAK {settings.api_key.strip()}"},
            params={"query": base, "size": 30},
            timeout=settings.timeout,
        )
        if response.status_code in {401, 403}:
            raise GeocodeError("KAKAO_AUTH", "카카오 REST 키가 거부됐습니다.")
        response.raise_for_status()
        doc = _candidate(response.json())
        road, jibun = _base_name(doc, "road_address"), _base_name(doc, "address")
        if not road and not jibun:
            raise ValueError("기본 주소가 없습니다.")
        if any(type(doc.get(key)) not in (str, int, float) for key in ("x", "y")):
            raise ValueError("좌표 형식이 잘못되었습니다.")
        site = Site(
            input_address=cleaned,
            road_address=road,
            jibun_address=jibun,
            detail_address=detail,
            latitude=float(doc["y"]),
            longitude=float(doc["x"]),
        )
        if (site.latitude, site.longitude) == (0, 0):
            raise ValueError("목업 좌표는 실제 주소로 확정할 수 없습니다.")
        if not any(_normalized(name) == normalized for name in (road, jibun) if name):
            raise GeocodeError(
                "ADDRESS_MISMATCH", "조회된 주소의 지역 또는 번지가 입력과 다릅니다."
            )
        return site
    except httpx.TimeoutException as exc:
        raise GeocodeError("UPSTREAM_TIMEOUT", "주소 조회 시간이 초과되었습니다.") from exc
    except httpx.HTTPError as exc:
        raise GeocodeError("UPSTREAM_FAILED", "주소 조회 서비스 연결에 실패했습니다.") from exc
    except (ValueError, TypeError, KeyError) as exc:
        raise GeocodeError(
            "BAD_RESPONSE", "주소 조회 응답의 구조 또는 좌표가 올바르지 않습니다."
        ) from exc
