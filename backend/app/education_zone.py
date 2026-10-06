"""V-World 교육환경보호구역 레이어를 좌표 하나로 조회합니다."""

from __future__ import annotations

import asyncio
import math
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.config import load_environment

# 기존 CLI 가져오기 경로를 맞춥니다.
load_dotenv_if_present = load_environment

VWORLD_DATA_URL = "https://api.vworld.kr/req/data"
# 국토교통부 교육환경보호구역. 교육지원청이 고시한 구역 폴리곤 그 자체입니다.
EDUCATION_ZONE_LAYER = "LT_C_UO101"
PAGE_SIZE = 1_000

# 같은 좌표에 절대·상대 구역이 겹칠 수 있어 재시도만 분기하고 결과는 모두 수집합니다.
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
RETRY_ERROR_CODES = {"SYSTEM_ERROR", "UNKNOWN_ERROR"}
# 재시도해도 같은 답이 옵니다. 바로 끊습니다.
FATAL_ERROR_CODES = {
    "INVALID_KEY",
    "INCORRECT_KEY",
    "UNAVAILABLE_KEY",
    "OVER_REQUEST_LIMIT",
    "PARAM_REQUIRED",
    "INVALID_TYPE",
    "INVALID_RANGE",
}
MAX_BACKOFF_S = 30.0
# Referer 없는 요청은 INCORRECT_KEY로 거절됩니다. 배포 주소가 생기면 바꿉니다.
DEFAULT_REFERER = "http://localhost:8000"
# 보호구역 조회 하나가 주소 단계를 오래 붙잡지 않게 합니다. 실측은 0.1초 수준입니다.
LOOKUP_TIMEOUT_S = 20.0


class EducationZoneError(Exception):
    """구역 조회 실패입니다. 키와 원문 응답은 메시지에 담지 않습니다."""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class EducationZoneSettings:
    api_key: str | None = field(default=None, repr=False)
    # Referer가 없으면 INCORRECT_KEY로 거절합니다(실측). 값 자체는 검증하지 않지만
    # 발급 때 등록한 URL을 넣어 둡니다. 나중에 검증이 켜져도 그대로 통과합니다.
    referer: str = DEFAULT_REFERER
    request_timeout_s: float = 15.0
    max_retries: int = 2
    retry_backoff_s: float = 1.5

    def __post_init__(self) -> None:
        if type(self.max_retries) is not int or not 0 <= self.max_retries <= 5:
            raise ValueError("재시도 횟수가 올바르지 않습니다.")
        if not isinstance(self.referer, str) or not self.referer.strip():
            raise ValueError("V-World Referer가 비어 있습니다.")
        for value in (self.request_timeout_s, self.retry_backoff_s):
            if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
                raise ValueError("구역 조회 제한시간과 대기 시간이 올바르지 않습니다.")

    @classmethod
    def from_env(cls) -> EducationZoneSettings:
        values: dict[str, object] = {
            "api_key": os.environ.get("VWORLD_API_KEY"),
            "referer": os.environ.get("VWORLD_REFERER"),
        }
        return cls(**{k: v for k, v in values.items() if v})  # type: ignore[arg-type]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Coordinate(Model):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class EducationZone(Model):
    """고시된 구역 한 건입니다. 값은 원문 그대로 보존합니다."""

    # uname. 실측 3종 — "절대보호구역" / "상대보호구역" / "교육환경보호구역".
    # 교육청마다 올리는 표기가 달라 절대·상대 구분이 없는 건도 있어 정규화하지 않습니다.
    name: str
    # remark. 실측에서 대부분 비어 있고, 교육청 확인 안내문이나 학교명이 섞여 옵니다.
    # 학교명 필드가 아니므로 그렇게 쓰지 않습니다.
    note: str | None = None
    notice_year: str | None = None
    notice_no: str | None = None
    sido: str | None = None
    sigungu: str | None = None
    geometry: dict[str, Any] | None = None


class ZoneError(Model):
    code: str
    message: str


class EducationZoneScan(Model):
    """status=ok이고 zones가 비면 보호구역이 아닙니다. 조회 실패(error)와 구분합니다."""

    status: Literal["ok", "error"]
    center: Coordinate
    queried_at: str
    zones: list[EducationZone] = Field(default_factory=list)
    error: ZoneError | None = None
    warnings: list[str] = Field(default_factory=list)


def failed_scan(latitude: float, longitude: float, code: str, message: str) -> EducationZoneScan:
    """조회를 시작도 못 했을 때 쓰는 실패 결과입니다. 보호구역 없음과 구분합니다."""
    return EducationZoneScan(
        status="error",
        center=Coordinate(latitude=latitude, longitude=longitude),
        queried_at=_now(),
        error=ZoneError(code=code, message=message),
    )


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _text(value: Any) -> str | None:
    """V-World는 빈 값을 ""로 보냅니다. 없음과 구분하지 않고 None으로 모읍니다."""
    if value is None:
        return None
    if not isinstance(value, (str, int, float)):
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _zone(feature: Any, *, with_geometry: bool) -> EducationZone | None:
    if not isinstance(feature, dict):
        raise EducationZoneError("BAD_RESPONSE", "구역 조회 응답의 항목 구조가 올바르지 않습니다.")
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise EducationZoneError("BAD_RESPONSE", "구역 조회 응답에 속성이 없습니다.")
    name = _text(properties.get("uname"))
    if name is None:
        # 구역명이 없으면 무엇에 걸렸는지 설명할 수 없어 버리고 경고로 남깁니다.
        return None
    geometry = feature.get("geometry") if with_geometry else None
    return EducationZone(
        name=name,
        note=_text(properties.get("remark")),
        notice_year=_text(properties.get("dyear")),
        notice_no=_text(properties.get("dnum")),
        sido=_text(properties.get("sido_name")),
        sigungu=_text(properties.get("sigg_name")),
        geometry=geometry if isinstance(geometry, dict) else None,
    )


def _features(result: Any) -> list[Any]:
    if not isinstance(result, dict):
        raise EducationZoneError("BAD_RESPONSE", "구역 조회 응답에 결과가 없습니다.")
    collection = result.get("featureCollection")
    if not isinstance(collection, dict):
        raise EducationZoneError("BAD_RESPONSE", "구역 조회 응답의 결과 구조가 올바르지 않습니다.")
    features = collection.get("features")
    if not isinstance(features, list):
        raise EducationZoneError("BAD_RESPONSE", "구역 조회 응답에 항목 목록이 없습니다.")
    return features


async def find_education_zones(
    latitude: float,
    longitude: float,
    *,
    with_geometry: bool = False,
    settings: EducationZoneSettings | None = None,
    client: httpx.AsyncClient | None = None,
) -> EducationZoneScan:
    """좌표가 포함된 교육환경보호구역을 조회합니다.

    거리를 계산하지 않습니다. 교육지원청이 고시한 구역 폴리곤에 좌표가 들어가는지를
    V-World가 판정하므로, 학교 출입문·경계까지의 거리를 따로 재지 않아도 됩니다.

    반경을 넓히면 "주변에 구역이 있다"가 섞여 들어오므로 점으로만 조회합니다.
    학교가 여럿이면 보호구역이 겹쳐 zones가 여러 건일 수 있습니다.
    하나라도 절대보호구역이면 금지이므로 전부 담아 돌려줍니다.

    반환값의 status=ok이고 zones가 비어 있으면 보호구역이 아니라는 뜻이며,
    조회 실패(status=error)와 반드시 구분해서 읽어야 합니다.

    설정·입력 오류와 해석할 수 없는 응답은 EducationZoneError로 올립니다.
    외부 호출 실패만 status=error로 모읍니다.
    """
    settings = settings or EducationZoneSettings.from_env()
    for value, low, high in ((latitude, -90.0, 90.0), (longitude, -180.0, 180.0)):
        if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
            raise EducationZoneError("INVALID_COORDINATE", "좌표 값이 올바르지 않습니다.")
    key = settings.api_key
    if not isinstance(key, str) or not key.strip():
        raise EducationZoneError("CONFIG_ERROR", "V-World 인증키가 설정되지 않았습니다.")

    if client is None:
        async with httpx.AsyncClient(timeout=settings.request_timeout_s) as owned:
            return await find_education_zones(
                latitude,
                longitude,
                with_geometry=with_geometry,
                settings=settings,
                client=owned,
            )

    center = Coordinate(latitude=latitude, longitude=longitude)
    params: dict[str, Any] = {
        "service": "data",
        "request": "GetFeature",
        "version": "2.0",
        "format": "json",
        "errorFormat": "json",
        "data": EDUCATION_ZONE_LAYER,
        # EPSG:4326 기준이라 경도가 x, 위도가 y입니다.
        "geomFilter": f"POINT({longitude} {latitude})",
        # 점으로만 봅니다. 50m·200m 거리는 이미 고시된 폴리곤에 들어 있습니다.
        "buffer": 0,
        "geometry": "true" if with_geometry else "false",
        "attribute": "true",
        "crs": "EPSG:4326",
        "size": PAGE_SIZE,
        "page": 1,
        "key": key.strip(),
    }
    # 값은 검증되지 않지만 헤더 자체가 없으면 INCORRECT_KEY로 거절됩니다.
    headers = {"Referer": settings.referer.strip()}

    def failed(code: str, message: str) -> EducationZoneScan:
        return EducationZoneScan(
            status="error",
            center=center,
            queried_at=_now(),
            error=ZoneError(code=code, message=message),
        )

    backoff = settings.retry_backoff_s
    last: EducationZoneScan | None = None
    for attempt in range(settings.max_retries + 1):
        try:
            response = await client.get(
                VWORLD_DATA_URL,
                params=params,
                headers=headers,
                timeout=settings.request_timeout_s,
            )
        except httpx.TimeoutException:
            last = failed("UPSTREAM_TIMEOUT", "구역 조회 응답 시간이 초과되었습니다.")
        except httpx.HTTPError:
            last = failed("UPSTREAM_FAILED", "구역 조회 서비스 연결에 실패했습니다.")
        else:
            if response.status_code in RETRY_STATUS_CODES:
                last = failed("UPSTREAM_FAILED", "구역 조회 서비스가 일시적으로 응답하지 않습니다.")
            elif response.status_code >= 400:
                return failed("UPSTREAM_FAILED", "구역 조회 요청이 거부되었습니다.")
            else:
                scan, retryable = _parse(response, center, with_geometry=with_geometry)
                if not retryable:
                    return scan
                last = scan
        if attempt < settings.max_retries:
            await asyncio.sleep(min(backoff * (attempt + 1), MAX_BACKOFF_S))

    assert last is not None
    return last


def _parse(
    response: httpx.Response,
    center: Coordinate,
    *,
    with_geometry: bool,
) -> tuple[EducationZoneScan, bool]:
    """(결과, 재시도 여부)를 돌려줍니다."""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    body = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(body, dict):
        raise EducationZoneError("BAD_RESPONSE", "구역 조회 응답 형식이 올바르지 않습니다.")

    status = body.get("status")
    queried_at = _now()

    if status == "NOT_FOUND":
        # 좌표가 어느 구역에도 들어가지 않은 정상 응답입니다.
        return (
            EducationZoneScan(status="ok", center=center, queried_at=queried_at),
            False,
        )

    if status == "ERROR":
        error = body.get("error")
        code = _text(error.get("code")) if isinstance(error, dict) else None
        code = code or "UNKNOWN_ERROR"
        if code in FATAL_ERROR_CODES:
            return (
                EducationZoneScan(
                    status="error",
                    center=center,
                    queried_at=queried_at,
                    error=ZoneError(code=code, message="구역 조회 서비스가 요청을 거절했습니다."),
                ),
                False,
            )
        return (
            EducationZoneScan(
                status="error",
                center=center,
                queried_at=queried_at,
                error=ZoneError(code=code, message="구역 조회 서비스에서 오류가 발생했습니다."),
            ),
            code in RETRY_ERROR_CODES,
        )

    if status != "OK":
        raise EducationZoneError("BAD_RESPONSE", "구역 조회 응답 상태를 해석할 수 없습니다.")

    features = _features(body.get("result"))
    warnings: list[str] = []
    zones: list[EducationZone] = []
    for feature in features:
        zone = _zone(feature, with_geometry=with_geometry)
        if zone is None:
            warnings.append("구역명이 없는 항목을 제외했습니다.")
            continue
        zones.append(zone)

    record = body.get("record")
    if isinstance(record, dict):
        try:
            total = int(str(record.get("total", len(features))))
        except (TypeError, ValueError):
            total = len(features)
        if total > len(features):
            warnings.append(f"조회된 구역 {total}건 중 {len(features)}건만 받았습니다.")

    return (
        EducationZoneScan(
            status="ok",
            center=center,
            queried_at=queried_at,
            zones=zones,
            warnings=warnings,
        ),
        False,
    )


def site_lookup(settings: EducationZoneSettings | None = None):
    """Site를 받는 조회 함수를 만듭니다. 인증키가 없으면 None이라 조회를 걸지 않습니다."""
    settings = settings or EducationZoneSettings.from_env()
    if not settings.api_key:
        return None

    async def lookup(site: Any) -> EducationZoneScan:
        return await find_education_zones(site.latitude, site.longitude, settings=settings)

    return lookup


async def scan_site(site: Any, lookup: Any, *, timeout_s: float = LOOKUP_TIMEOUT_S):
    """조회 실패를 결과로 바꿔 돌려줍니다. 보호구역 하나로 분석을 멈추지 않습니다."""
    if lookup is None:
        return None
    try:
        async with asyncio.timeout(timeout_s):
            return EducationZoneScan.model_validate(await lookup(site))
    except TimeoutError:
        return failed_scan(
            site.latitude, site.longitude, "ZONE_TIMEOUT", "구역 조회 시간이 초과되었습니다."
        )
    except Exception:
        return failed_scan(
            site.latitude, site.longitude, "ZONE_FAILED", "구역 조회에 실패했습니다."
        )
