"""건축HUB 건축물대장(표제부·층별개요·호실·오수정화시설)을 주소 하나로 조회합니다.

건축HUB는 주소가 아니라 지번 코드(시군구·법정동·대지구분·번·지)로 조회합니다.
카카오 주소 검색의 지번 주소에 이 코드가 함께 오므로 같은 키로 먼저 찾습니다.
값의 표기는 상가 정보 확인 화면(frontend/lib/api/building.ts)에 맞춰 보냅니다.
"""

from __future__ import annotations

import asyncio
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.address import KAKAO_ADDRESS_URL, GeocodeError, _candidate, matched_addresses, split_detail
from app.config import AddressSettings

HUB_URL = "https://apis.data.go.kr/1613000/BldRgstHubService"
TITLE, FLOOR, UNIT, SEWAGE = (
    "getBrTitleInfo",
    "getBrFlrOulnInfo",
    "getBrExposPubuseAreaInfo",
    "getBrWclfInfo",
)
PAGE_SIZE = 100
# 3,000행. 전유공용면적은 호실마다 전유·공용 행이 따로 와서 표제부보다 훨씬 깁니다.
MAX_PAGES = 30
# 표제부의 옥내·옥외 기계식·자주식 주차 대수입니다. 합이 건물 전체 주차 대수입니다.
PARKING_FIELDS = ("indrMechUtcnt", "oudrMechUtcnt", "indrAutoUtcnt", "oudrAutoUtcnt")
# 건축HUB는 지하층을 "지1층"·"지1"로 줍니다. 화면 표기("지하 1층")로 바꿉니다.
BASEMENT = re.compile(r"지(?:하)?\s*(\d+)\s*층?")
GROUND = re.compile(r"(?:지상\s*)?(\d+)\s*층")

# 화면의 오수정화시설 선택지입니다(SEWAGE_OPTIONS에서 사용자 몫인 '모름'만 뺌).
SewageMethod = Literal["하수종말처리장 연결", "정화조", "오수처리시설"]
# 형식코드명(modeCdNm) 예: 하수종말처리장연결, 부패탱크방법. 부패탱크방법이 정화조입니다.
# 접촉폭기방법·살수여상방법처럼 처리 방식 이름만 있으면 선택지를 정할 수 없어 맞추지 않습니다.
SEWAGE_KEYWORDS: tuple[tuple[str, SewageMethod], ...] = (
    ("하수종말", "하수종말처리장 연결"),
    ("부패탱크", "정화조"),
    ("정화조", "정화조"),
    ("오수처리", "오수처리시설"),
)


class BuildingRegistryError(Exception):
    """건축HUB 조회 실패입니다. 키와 원문 응답은 메시지에 담지 않습니다."""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class BuildingRegistrySettings:
    # 공공데이터포털 일반 인증키. Encoding·Decoding 두 개가 보이면 Decoding입니다(httpx가 인코딩).
    api_key: str | None = field(default=None, repr=False)
    # 정상 응답은 1초 안에 옵니다. 게이트웨이도 5초면 503으로 끊습니다.
    timeout: float = 10.0
    # 일시 오류(5xx·빈 응답·시간 초과·연결 실패)를 다시 요청하는 횟수와 간격(초, 회차마다 늘림)
    retries: int = 2
    retry_delay: float = 0.5

    @classmethod
    def from_env(cls) -> BuildingRegistrySettings:
        return cls(api_key=os.environ.get("BUILDING_REGISTRY_API_KEY"))


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BuildingTitle(Model):
    """표제부 한 동입니다."""

    dong_name: str | None = Field(description="동 이름. 한 지번에 건물이 여럿일 때 구분합니다.")
    building_name: str | None
    main_use: str | None = Field(description="주용도. 예: 제2종근린생활시설")
    ground_floors: int | None
    underground_floors: int | None
    total_area_m2: float | None = Field(description="연면적(㎡)")
    parking_spaces: int | None = Field(
        description="주차 대수. 옥내·옥외 기계식·자주식 합. 넷 다 비어 있으면 null"
    )


class FloorOverview(Model):
    """층별개요 한 행입니다. 한 층에 용도가 여럿이면 여러 행입니다."""

    dong_name: str | None
    floor: str | None = Field(description="예: 4층, 지하 1층")
    use: str | None = Field(description="용도(대장 주용도코드명). 예: 일반음식점")
    use_detail: str | None = Field(description="기타용도(대장 원문). 예: 제2종근린생활시설")
    area_m2: float | None


class Unit(Model):
    """호실 하나입니다. 면적은 전유 부분만 더한 값입니다."""

    dong_name: str | None
    unit_name: str | None = Field(description="호수. 예: 401호")
    floor: str | None = Field(description="예: 4층, 지하 1층")
    use: str | None = Field(description="용도(대장 주용도코드명). 예: 학원")
    use_detail: str | None = Field(description="기타용도(대장 원문). 예: 교육연구시설(학원)")
    area_m2: float | None = Field(description="전용면적(㎡)")


class SewageFacility(Model):
    """오수정화시설 한 건입니다."""

    method: SewageMethod | None = Field(
        description="화면 선택지로 맞춘 처리 방식. 맞출 수 없는 형식이면 null"
    )
    method_name: str | None = Field(
        description="대장 원문 형식(형식코드명, 비어 있으면 기타형식). 예: 접촉폭기방법"
    )


class BuildingRegistry(Model):
    """목록이 null이면 그 항목 조회가 실패한 것이고, []이면 등록된 행이 없는 것입니다."""

    road_address: str | None
    jibun_address: str | None
    titles: list[BuildingTitle] | None = Field(
        description="연면적이 큰 건물부터. 한 지번에 건물이 여럿이면 titles[0]이 대표 건물"
    )
    floors: list[FloorOverview] | None
    units: list[Unit] | None
    sewage: list[SewageFacility] | None


def _text(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _count(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _floor(row: dict[str, Any]) -> str | None:
    text = _text(row.get("flrNoNm"))
    if text and (match := BASEMENT.fullmatch(text)):
        return f"지하 {int(match.group(1))}층"
    if text and (match := GROUND.fullmatch(text)):
        return f"{int(match.group(1))}층"
    number = _count(row.get("flrNo"))
    kind = str(row.get("flrGbCd") or "").strip()
    if (number or 0) > 0 and kind in {"10", "20"}:
        return f"지하 {number}층" if kind == "10" else f"{number}층"
    return text


async def _parcel(
    client: httpx.AsyncClient, address: str, settings: AddressSettings
) -> tuple[dict[str, str], str | None, str | None]:
    """주소를 건축HUB 조회 코드와 도로명·지번 주소로 바꿉니다."""
    base, _ = split_detail(address)
    if not base:
        raise GeocodeError("EMPTY_ADDRESS", "주소가 비어 있습니다.")
    if not settings.api_key or not settings.api_key.strip():
        raise GeocodeError("ADDRESS_CONFIG_ERROR", "카카오 REST 키를 확인하세요.")
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
        road_name, jibun_name = matched_addresses(address, doc)
        jibun = doc.get("address")
        if not isinstance(jibun, dict):
            raise GeocodeError("NOT_FOUND", "지번 주소를 찾지 못했습니다.")
        code = str(jibun.get("b_code") or "")
        if len(code) != 10 or not code.isdigit():
            raise ValueError("법정동 코드가 올바르지 않습니다.")
        return (
            {
                "sigunguCd": code[:5],
                "bjdongCd": code[5:],
                # 0 대지, 1 산
                "platGbCd": "1" if jibun.get("mountain_yn") == "Y" else "0",
                "bun": str(jibun.get("main_address_no") or "0").zfill(4),
                "ji": str(jibun.get("sub_address_no") or "0").zfill(4),
            },
            road_name,
            jibun_name,
        )
    except httpx.TimeoutException as exc:
        raise GeocodeError("UPSTREAM_TIMEOUT", "주소 조회 시간이 초과되었습니다.") from exc
    except httpx.HTTPError as exc:
        raise GeocodeError("UPSTREAM_FAILED", "주소 조회 서비스 연결에 실패했습니다.") from exc
    except (ValueError, TypeError, KeyError) as exc:
        raise GeocodeError("BAD_RESPONSE", "주소 조회 응답 구조가 올바르지 않습니다.") from exc


async def _fetch(
    client: httpx.AsyncClient,
    operation: str,
    params: dict[str, Any],
    settings: BuildingRegistrySettings,
) -> httpx.Response:
    """공공데이터포털 게이트웨이는 쉬다가 깨어날 때 503이나 빈 200 응답을 잠깐 줍니다.

    그런 일시 오류만 잠시 뒤 다시 요청합니다. 인증 오류나 결과 코드 오류는 그대로 돌려줍니다.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            response = await client.get(
                f"{HUB_URL}/{operation}", params=params, timeout=settings.timeout
            )
        except httpx.TransportError:
            if attempt > settings.retries:
                raise
        else:
            empty = response.status_code == 200 and not response.content.strip()
            transient = response.status_code >= 500 or empty
            if not transient or attempt > settings.retries:
                return response
        await asyncio.sleep(settings.retry_delay * attempt)


def _result_code(code: str) -> None:
    if code in {"22"}:
        raise BuildingRegistryError("RATE_LIMIT", "건축HUB 호출 한도를 초과했습니다.")
    if code in {"20", "21", "30", "31", "32", "33"}:
        raise BuildingRegistryError("AUTH", "건축HUB 인증키 또는 사용 권한을 확인하세요.")
    if code not in {"00", "03"}:
        raise BuildingRegistryError("UPSTREAM_ERROR", "건축HUB가 오류를 반환했습니다.")


async def _items(
    client: httpx.AsyncClient,
    operation: str,
    parcel: dict[str, str],
    settings: BuildingRegistrySettings,
) -> list[dict[str, Any]]:
    """한 오퍼레이션의 모든 페이지를 모읍니다."""
    rows: list[dict[str, Any]] = []
    try:
        for page in range(1, MAX_PAGES + 1):
            response = await _fetch(
                client,
                operation,
                {
                    **parcel,
                    "serviceKey": settings.api_key,
                    "_type": "json",
                    "numOfRows": PAGE_SIZE,
                    "pageNo": page,
                },
                settings,
            )
            if response.status_code in {401, 403}:
                raise BuildingRegistryError("AUTH", "건축HUB 인증키가 거부됐습니다.")
            if response.status_code == 429:
                raise BuildingRegistryError("RATE_LIMIT", "건축HUB 호출 한도를 초과했습니다.")
            response.raise_for_status()
            # 미등록 키 등 게이트웨이 오류는 _type=json이어도 XML로 옵니다.
            if response.content.removeprefix(b"\xef\xbb\xbf").lstrip().startswith(b"<"):
                root = ET.fromstring(response.content)
                code = next(
                    (
                        node.text
                        for node in root.iter()
                        if node.tag.rsplit("}", 1)[-1] == "returnReasonCode"
                    ),
                    "",
                )
                _result_code(str(code).strip())
                raise ValueError("JSON 응답이 아닙니다.")
            body = response.json()["response"]
            code = str(body["header"]["resultCode"])
            _result_code(code)
            # 공공데이터포털 공통 코드 03(NODATA_ERROR)은 실패가 아니라 행이 없다는 뜻입니다.
            if code == "03":
                return rows
            result = body.get("body") or {}
            # 결과가 없으면 items가 빈 문자열, 한 건이면 item이 객체로 옵니다.
            items = result.get("items")
            item = items.get("item") if isinstance(items, dict) else None
            page_rows = [item] if isinstance(item, dict) else item or []
            rows += [row for row in page_rows if isinstance(row, dict)]
            if not page_rows or len(rows) >= (_count(result.get("totalCount")) or 0):
                return rows
    except httpx.TimeoutException:
        raise BuildingRegistryError("UPSTREAM_TIMEOUT", "건축HUB 시간 초과입니다.") from None
    except httpx.HTTPError:
        raise BuildingRegistryError("UPSTREAM_FAILED", "건축HUB 연결에 실패했습니다.") from None
    except (ValueError, TypeError, KeyError, ET.ParseError):
        raise BuildingRegistryError("BAD_RESPONSE", "건축HUB 응답 구조가 다릅니다.") from None
    raise BuildingRegistryError("TOO_MANY_ROWS", f"{operation} 결과가 {len(rows)}행을 넘습니다.")


def _parking(row: dict[str, Any]) -> int | None:
    counts = [count for key in PARKING_FIELDS if (count := _count(row.get(key))) is not None]
    return sum(counts) if counts else None


def _titles(rows: list[dict[str, Any]]) -> list[BuildingTitle]:
    """한 지번에 건물이 여럿일 수 있어(예: 단독주택과 상가 건물) 연면적이 큰 건물을 앞에 둡니다."""
    titles = [
        BuildingTitle(
            dong_name=_text(row.get("dongNm")),
            building_name=_text(row.get("bldNm")),
            main_use=_text(row.get("mainPurpsCdNm")),
            ground_floors=_count(row.get("grndFlrCnt")),
            underground_floors=_count(row.get("ugrndFlrCnt")),
            total_area_m2=_number(row.get("totArea")),
            parking_spaces=_parking(row),
        )
        for row in rows
    ]
    return sorted(titles, key=lambda title: title.total_area_m2 or 0, reverse=True)


def _floors(rows: list[dict[str, Any]]) -> list[FloorOverview]:
    return [
        FloorOverview(
            dong_name=_text(row.get("dongNm")),
            floor=_floor(row),
            use=_text(row.get("mainPurpsCdNm")),
            use_detail=_text(row.get("etcPurps")),
            area_m2=_number(row.get("area")),
        )
        for row in rows
    ]


def _units(rows: list[dict[str, Any]]) -> list[Unit]:
    """전유 행만 골라 동·호수별로 면적을 더합니다. 공용 행은 버립니다."""
    units: dict[tuple[str | None, str | None], Unit] = {}
    for row in rows:
        if _text(row.get("exposPubuseGbCdNm")) != "전유":
            continue
        key = (_text(row.get("dongNm")), _text(row.get("hoNm")))
        area = _number(row.get("area"))
        if key in units:
            unit = units[key]
            if area is not None:
                unit.area_m2 = round((unit.area_m2 or 0) + area, 2)
            continue
        units[key] = Unit(
            dong_name=key[0],
            unit_name=key[1],
            floor=_floor(row),
            use=_text(row.get("mainPurpsCdNm")),
            use_detail=_text(row.get("etcPurps")),
            area_m2=area,
        )
    return list(units.values())


def _sewage(rows: list[dict[str, Any]]) -> list[SewageFacility]:
    """형식코드명이 비면 기타형식(etcMode) 원문을 씁니다. 둘 다 빈 행은 뺍니다."""
    facilities = []
    for row in rows:
        names = [name for key in ("modeCdNm", "etcMode") if (name := _text(row.get(key)))]
        if not names:
            continue
        method = next((m for name in names for word, m in SEWAGE_KEYWORDS if word in name), None)
        facilities.append(SewageFacility(method=method, method_name=names[0]))
    return facilities


async def lookup_building(
    address: str,
    settings: BuildingRegistrySettings | None = None,
    address_settings: AddressSettings | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> BuildingRegistry:
    """네 항목을 동시에 조회합니다. 일부만 실패하면 그 항목만 null로 돌려줍니다."""
    settings = settings or BuildingRegistrySettings.from_env()
    if not settings.api_key or not settings.api_key.strip():
        raise BuildingRegistryError("CONFIG_ERROR", "건축HUB 인증키가 설정되지 않았습니다.")
    if client is None:
        async with httpx.AsyncClient() as owned:
            return await lookup_building(address, settings, address_settings, client=owned)
    parcel, road, jibun = await _parcel(
        client, address.strip(), address_settings or AddressSettings.from_env()
    )
    results = await asyncio.gather(
        *(_items(client, op, parcel, settings) for op in (TITLE, FLOOR, UNIT, SEWAGE)),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, BaseException) and not isinstance(result, BuildingRegistryError):
            raise result
    if all(isinstance(result, BuildingRegistryError) for result in results):
        raise results[0]  # type: ignore[misc]
    titles, floors, units, sewage = (None if isinstance(r, BaseException) else r for r in results)
    return BuildingRegistry(
        road_address=road,
        jibun_address=jibun,
        titles=None if titles is None else _titles(titles),
        floors=None if floors is None else _floors(floors),
        units=None if units is None else _units(units),
        sewage=None if sewage is None else _sewage(sewage),
    )
