"""소상공인시장진흥공단 상가정보 API를 호출합니다."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from weakref import WeakKeyDictionary

import httpx

from app.storage.raw import RawStorageError, capture_http, current_capture, scrub

from .config import (
    SBIZ_BASE_URL,
    SBIZ_DISTRICT_OPERATION,
    SBIZ_RADIUS_OPERATION,
    Settings,
)
from .schemas import Store

REFERENCE_DATE_KEYS = ("stdrDt", "dataStdDe", "baseYm", "stdrYm")
NODATA_RESULT_CODES = {"03"}
NODATA_KEYWORDS = ("NODATA", "NO_DATA", "데이터없음", "데이터가_없")
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_RETRY_BACKOFF_S = 1.5
RAW_CACHE_VERSION = 2


class SbizApiError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class RadiusRejectedError(SbizApiError):
    pass


class NoDataError(SbizApiError):
    pass


def _cache_path(settings: Settings, key: str) -> Path:
    return settings.cache_dir / f"raw-v{RAW_CACHE_VERSION}_{key}.json"


def _read_cache(path: Path, ttl_hours: int) -> Any | None:
    try:
        if not path.exists() or time.time() - path.stat().st_mtime > ttl_hours * 3600:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("version") != RAW_CACHE_VERSION:
            return None
        if (
            not isinstance(payload.get("meta"), dict)
            or not isinstance(payload.get("pages"), list)
            or not payload["pages"]
        ):
            return None
        items = []
        for page in payload["pages"]:
            if (
                not isinstance(page, dict)
                or not isinstance(page.get("payload"), dict)
                or not isinstance(page.get("request_args"), dict)
                or not isinstance(page.get("collected_at"), str)
            ):
                return None
            _check_header(page["payload"])
            items.extend(_extract_items(page["payload"])[0])
        if len(items) != payload["meta"].get("fetched"):
            return None
        return {**payload, "items": items}
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, SbizApiError, TypeError, KeyError):
        return None


def _write_cache(path: Path, payload: Any) -> None:
    if not payload["pages"]:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"version": RAW_CACHE_VERSION, "pages": payload["pages"], "meta": payload["meta"]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


async def _capture_cache(cached, cache_key):
    capture = current_capture()
    if capture is not None:
        for page in cached["pages"]:
            await capture.record(
                source="commercial_area",
                source_type="api",
                args={
                    **page["request_args"],
                    "cache_hit": True,
                    "cache_key": cache_key,
                    "original_collected_at": page["collected_at"],
                },
                page=page["page"],
                status=page["http_status"],
                payload=page["payload"],
            )


def snap_to_grid(value: float, grid_m: int) -> float:
    degrees = grid_m / 111_000
    if degrees <= 0:
        return value
    return round(round(value / degrees) * degrees, 6)


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    if "response" in payload and isinstance(payload["response"], dict):
        return payload["response"]
    return payload


def _check_header(payload: dict[str, Any]) -> None:
    header = _unwrap(payload).get("header")
    if header is None:
        header = {}
    if not isinstance(header, dict):
        raise SbizApiError("BAD_RESPONSE", "상가정보 API 응답 형식이 올바르지 않습니다.")
    code = str(header.get("resultCode", "")).strip()
    message = str(header.get("resultMsg", "")).strip()
    if code and code not in {"00", "0"}:
        normalized = message.upper().replace("-", "_").replace(" ", "_")
        if code in NODATA_RESULT_CODES or any(k in normalized for k in NODATA_KEYWORDS):
            raise NoDataError(code, message)
        if "radius" in message.lower() or "반경" in message:
            raise RadiusRejectedError(code, message)
        raise SbizApiError(code, message or "unknown error")


def _extract_items(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    body = _unwrap(payload).get("body")
    if not isinstance(body, dict) or "items" not in body:
        raise SbizApiError("BAD_RESPONSE", "상가정보 API 응답 형식이 올바르지 않습니다.")
    items = body.get("items")
    if isinstance(items, dict):
        items = items.get("item") or []
    if items is None:
        items = []
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        raise SbizApiError("BAD_RESPONSE", "상가정보 API 응답 형식이 올바르지 않습니다.")
    if not all(isinstance(item, dict) for item in items):
        raise SbizApiError("BAD_RESPONSE", "상가정보 API 응답 형식이 올바르지 않습니다.")
    total: Any = body.get("totalCount")
    try:
        total_count = int(total)
    except (TypeError, ValueError):
        total_count = len(items)
    return list(items), total_count


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def to_store(item: dict[str, Any]) -> Store | None:
    major_code = _clean(item.get("indsLclsCd"))
    middle_code = _clean(item.get("indsMclsCd"))
    if not major_code or not middle_code:
        return None
    return Store(
        store_id=_clean(item.get("bizesId")) or "",
        name=_clean(item.get("bizesNm")) or "",
        branch_name=_clean(item.get("brchNm")),
        major_code=major_code,
        major_name=_clean(item.get("indsLclsNm")) or major_code,
        middle_code=middle_code,
        middle_name=_clean(item.get("indsMclsNm")) or middle_code,
        small_code=_clean(item.get("indsSclsCd")),
        small_name=_clean(item.get("indsSclsNm")),
        latitude=_to_float(item.get("lat")),
        longitude=_to_float(item.get("lon")),
        road_address=_clean(item.get("rdnmAdr")),
        district_code=_clean(item.get("signguCd")),
        district_name=_clean(item.get("signguNm")),
    )


def reference_date_of(items: list[dict[str, Any]]) -> str | None:
    for item in items:
        for key in REFERENCE_DATE_KEYS:
            value = _clean(item.get(key))
            if value:
                return value
    return None


def _to_stores(items: list[dict[str, Any]]) -> list[Store]:
    """대용량 캐시 변환을 작업 스레드에서 한 번에 처리합니다."""
    return [store for item in items if (store := to_store(item)) is not None]


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        seconds = float(raw)
        return min(seconds, 30.0) if math.isfinite(seconds) and seconds >= 0 else None
    except ValueError:
        return None


_REQUEST_LIMITS: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    WeakKeyDictionary()
)


def _request_limit(max_concurrency: int) -> asyncio.Semaphore:
    # ponytail: 서버 워커의 단일 루프에서 공유합니다. 다중 프로세스 쿼터는 별도 조정이 필요합니다.
    # 같은 워커는 최초 설정을 유지하며 요청마다 한도를 늘리지 않습니다.
    loop = asyncio.get_running_loop()
    if loop not in _REQUEST_LIMITS:
        _REQUEST_LIMITS[loop] = asyncio.Semaphore(max(1, max_concurrency))
    return _REQUEST_LIMITS[loop]


class StoreClient:
    """상가정보 API 비동기 클라이언트입니다.

    분석 한 번이 반경·기준선·자치구 조회로 100회가 넘는 요청을 만듭니다.
    첫 페이지에서 전체 건수를 확인한 뒤 나머지 페이지를 동시에 받아오되,
    일일 쿼터와 429를 고려해 동시 요청 수를 max_concurrency로 제한합니다.
    """

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client
        self._owns_client = client is None
        self.calls_made = 0

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.settings.request_timeout_s,
                limits=httpx.Limits(max_connections=self.settings.max_concurrency),
            )
            self._owns_client = True
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None

    async def __aenter__(self) -> StoreClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def _request_page(
        self, lat: float, lon: float, radius_m: int, page: int
    ) -> dict[str, Any]:
        return await self._request(
            SBIZ_RADIUS_OPERATION,
            {"radius": radius_m, "cx": lon, "cy": lat},
            page,
        )

    async def _request_district_page(self, signgu_cd: str, page: int) -> dict[str, Any]:
        return await self._request(
            SBIZ_DISTRICT_OPERATION,
            {"divId": "signguCd", "key": signgu_cd},
            page,
        )

    async def _request(self, operation: str, query: dict[str, Any], page: int) -> dict[str, Any]:
        if not self.settings.sbiz_service_key:
            raise SbizApiError("NO_KEY", "COMMERCIAL_AREA_API_KEY가 설정되지 않았습니다.")
        params = {
            "serviceKey": self.settings.sbiz_service_key,
            "type": "json",
            "numOfRows": self.settings.page_size,
            "pageNo": page,
            **query,
        }
        url = f"{SBIZ_BASE_URL}/{operation}"
        base_backoff = self.settings.retry_backoff_s
        if not math.isfinite(base_backoff) or base_backoff < 0:
            base_backoff = DEFAULT_RETRY_BACKOFF_S

        for attempt in range(self.settings.max_retries + 1):
            wait_s = min(base_backoff * (attempt + 1), 30.0)
            try:
                async with _request_limit(self.settings.max_concurrency):
                    response = await self._http().get(url, params=params)
                self.calls_made += 1
                await capture_http(
                    "commercial_area",
                    response,
                    secrets=[self.settings.sbiz_service_key],
                    page=str(page),
                    args={"url": url, "operation": operation, "query": params},
                )
                if response.status_code in RETRY_STATUS_CODES:
                    wait_s = _retry_after_seconds(response) or wait_s
                    raise httpx.HTTPStatusError(
                        f"status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                try:
                    payload = response.json()
                except json.JSONDecodeError as decode_error:
                    raise SbizApiError(
                        "BAD_RESPONSE", "상가정보 API 응답 형식이 올바르지 않습니다."
                    ) from decode_error
                if not isinstance(payload, dict):
                    raise SbizApiError(
                        "BAD_RESPONSE", "상가정보 API 응답 형식이 올바르지 않습니다."
                    )
                _check_header(payload)
                return payload
            except SbizApiError:
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in RETRY_STATUS_CODES:
                    raise SbizApiError(
                        "UPSTREAM_FAILED", "상가정보 API 조회에 실패했습니다."
                    ) from exc
                if attempt < self.settings.max_retries:
                    await asyncio.sleep(wait_s)
                    continue
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt < self.settings.max_retries:
                    await asyncio.sleep(wait_s)
                    continue
            except httpx.HTTPError as exc:
                raise SbizApiError(
                    "BAD_RESPONSE", "상가정보 API 응답 처리에 실패했습니다."
                ) from exc
        raise SbizApiError("UPSTREAM_FAILED", "상가정보 API 조회에 실패했습니다.")

    async def _collect_pages(
        self,
        fetch_page: Callable[[int], Awaitable[dict[str, Any]]],
        max_pages: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """첫 페이지로 전체 건수를 확인하고 나머지 페이지를 동시에 받아옵니다."""
        try:
            payload = await fetch_page(1)
        except NoDataError:
            return [], 0

        items, total_count = _extract_items(payload)
        if not items or len(items) >= total_count:
            return items, total_count

        page_size = max(1, self.settings.page_size)
        last_page = min(max_pages, -(-total_count // page_size))
        if last_page <= 1:
            return items, total_count

        pages = iter(range(2, last_page + 1))
        results: dict[int, list[dict[str, Any]]] = {}

        async def worker() -> None:
            for page in pages:
                try:
                    page_payload = await fetch_page(page)
                except NoDataError:
                    results[page] = []
                else:
                    results[page] = _extract_items(page_payload)[0]

        # 한 페이지가 실패하면 남은 요청을 취소한다.
        # gather 는 예외만 올려보내고 나머지를 계속 돌려서, 어차피 버릴 조회에
        # 쿼터를 그대로 쓴다. 자치구 조회는 67페이지라 손실이 크다.
        # 페이지 전부를 공유 슬롯 대기열에 넣지 않고 진행 중인 수만큼만 요청합니다.
        try:
            async with asyncio.TaskGroup() as group:
                for _ in range(min(last_page - 1, max(1, self.settings.max_concurrency))):
                    group.create_task(worker())
        except* RawStorageError as storage_failures:
            raise storage_failures.exceptions[0] from None
        except* SbizApiError as failures:
            raise failures.exceptions[0] from None

        for page in range(2, last_page + 1):
            items.extend(results[page])
        return items, total_count

    async def _collect_raw(self, fetch_page, max_pages, operation, query):
        pages = []

        async def fetch(page):
            payload = await fetch_page(page)
            pages.append(
                {
                    "page": str(page),
                    "http_status": 200,
                    "collected_at": datetime.now(UTC).isoformat(),
                    "request_args": {
                        "operation": operation,
                        "query": {
                            **query,
                            "type": "json",
                            "numOfRows": self.settings.page_size,
                            "pageNo": page,
                        },
                    },
                    "payload": scrub(payload, [self.settings.sbiz_service_key]),
                }
            )
            return payload

        items, total = await self._collect_pages(fetch, max_pages)
        return items, total, sorted(pages, key=lambda p: int(p["page"]))

    async def stores_in_radius(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        use_cache: bool = True,
        grid_m: int | None = None,
    ) -> tuple[list[Store], dict[str, Any]]:
        cache_lat = snap_to_grid(lat, grid_m) if grid_m else round(lat, 6)
        cache_lon = snap_to_grid(lon, grid_m) if grid_m else round(lon, 6)
        cache_key = f"radius_{radius_m}_{cache_lat}_{cache_lon}"
        path = await asyncio.to_thread(_cache_path, self.settings, cache_key)

        if use_cache:
            cached = await asyncio.to_thread(_read_cache, path, self.settings.cache_ttl_hours)
            if cached is not None:
                await _capture_cache(cached, cache_key)
                stores = await asyncio.to_thread(_to_stores, cached["items"])
                return stores, {**cached["meta"], "from_cache": True}

        items, total_count, pages = await self._collect_raw(
            lambda page: self._request_page(cache_lat, cache_lon, radius_m, page),
            self.settings.max_pages,
            SBIZ_RADIUS_OPERATION,
            {"radius": radius_m, "cx": cache_lon, "cy": cache_lat},
        )

        meta = {
            "total_count": total_count,
            "fetched": len(items),
            "truncated": len(items) < total_count,
            "radius_m": radius_m,
            "reference_date": await asyncio.to_thread(reference_date_of, items),
            "from_cache": False,
        }
        if use_cache:
            await asyncio.to_thread(_write_cache, path, {"pages": pages, "meta": meta})

        stores = await asyncio.to_thread(_to_stores, items)
        return stores, meta

    async def stores_in_radius_with_fallback(
        self,
        lat: float,
        lon: float,
        candidates: tuple[int, ...],
        grid_m: int | None = None,
    ) -> tuple[list[Store], dict[str, Any]]:
        last_error: SbizApiError | None = None
        for radius_m in candidates:
            try:
                return await self.stores_in_radius(lat, lon, radius_m, grid_m=grid_m)
            except RadiusRejectedError as exc:
                last_error = exc
                continue
            except SbizApiError as exc:
                last_error = exc
                if "radius" in exc.message.lower() or "반경" in exc.message:
                    continue
                raise
        raise last_error or SbizApiError("NO_RADIUS", "사용 가능한 반경을 찾지 못했습니다.")

    async def stores_in_district(self, signgu_cd: str) -> tuple[list[Store], dict[str, Any]]:
        cache_key = f"district_{signgu_cd}"
        path = await asyncio.to_thread(_cache_path, self.settings, cache_key)
        cached = await asyncio.to_thread(_read_cache, path, self.settings.district_cache_ttl_hours)
        if cached is not None:
            await _capture_cache(cached, cache_key)
            stores = await asyncio.to_thread(_to_stores, cached["items"])
            return stores, {**cached["meta"], "from_cache": True}

        items, total_count, pages = await self._collect_raw(
            lambda page: self._request_district_page(signgu_cd, page),
            self.settings.district_max_pages,
            SBIZ_DISTRICT_OPERATION,
            {"divId": "signguCd", "key": signgu_cd},
        )

        meta = {
            "signgu_cd": signgu_cd,
            "total_count": total_count,
            "fetched": len(items),
            "truncated": len(items) < total_count,
            "reference_date": await asyncio.to_thread(reference_date_of, items),
            "from_cache": False,
        }
        await asyncio.to_thread(_write_cache, path, {"pages": pages, "meta": meta})

        stores = await asyncio.to_thread(_to_stores, items)
        return stores, meta


CSV_FIELDS = {
    "bizesId": "상가업소번호",
    "bizesNm": "상호명",
    "brchNm": "지점명",
    "indsLclsCd": "상권업종대분류코드",
    "indsLclsNm": "상권업종대분류명",
    "indsMclsCd": "상권업종중분류코드",
    "indsMclsNm": "상권업종중분류명",
    "indsSclsCd": "상권업종소분류코드",
    "indsSclsNm": "상권업종소분류명",
    "lat": "위도",
    "lon": "경도",
    "rdnmAdr": "도로명주소",
    "signguCd": "시군구코드",
    "signguNm": "시군구명",
}
