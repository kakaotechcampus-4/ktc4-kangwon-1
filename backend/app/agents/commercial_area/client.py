"""소상공인시장진흥공단 상가정보 API를 호출합니다."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import httpx

from .config import SBIZ_BASE_URL, SBIZ_RADIUS_OPERATION, Settings
from .schemas import Store

REFERENCE_DATE_KEYS = ("stdrDt", "dataStdDe", "baseYm", "stdrYm")
NODATA_RESULT_CODES = {"03"}
NODATA_KEYWORDS = ("NODATA", "NO_DATA", "데이터없음", "데이터가_없")


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
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    return settings.cache_dir / f"{key}.json"


def _read_cache(path: Path, ttl_hours: int) -> Any | None:
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > ttl_hours * 3600:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(path: Path, payload: Any) -> None:
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


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
    header = _unwrap(payload).get("header") or {}
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
    body = _unwrap(payload).get("body") or {}
    items = body.get("items")
    if isinstance(items, dict):
        items = items.get("item") or []
    if items is None:
        items = []
    if isinstance(items, dict):
        items = [items]
    total = body.get("totalCount")
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
    )


def reference_date_of(items: list[dict[str, Any]]) -> str | None:
    for item in items:
        for key in REFERENCE_DATE_KEYS:
            value = _clean(item.get(key))
            if value:
                return value
    return None


class StoreClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client
        self.calls_made = 0

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.settings.request_timeout_s)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _request_page(self, lat: float, lon: float, radius_m: int, page: int) -> dict[str, Any]:
        if not self.settings.sbiz_service_key:
            raise SbizApiError("NO_KEY", "SBIZ_SERVICE_KEY가 설정되지 않았습니다.")
        params = {
            "serviceKey": self.settings.sbiz_service_key,
            "type": "json",
            "radius": radius_m,
            "cx": lon,
            "cy": lat,
            "numOfRows": self.settings.page_size,
            "pageNo": page,
        }
        url = f"{SBIZ_BASE_URL}/{SBIZ_RADIUS_OPERATION}"

        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = self._http().get(url, params=params)
                self.calls_made += 1
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise httpx.HTTPStatusError(
                        f"status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                try:
                    payload = response.json()
                except json.JSONDecodeError:
                    raise SbizApiError("BAD_RESPONSE", response.text[:200].replace("\n", " "))
                _check_header(payload)
                return payload
            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_error = exc
                if attempt < self.settings.max_retries:
                    time.sleep(self.settings.retry_backoff_s * (attempt + 1))
                    continue
        raise SbizApiError("UPSTREAM_FAILED", str(last_error))

    def stores_in_radius(
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
        path = _cache_path(self.settings, cache_key)

        if use_cache:
            cached = _read_cache(path, self.settings.cache_ttl_hours)
            if cached is not None:
                stores = [s for s in (to_store(i) for i in cached["items"]) if s]
                return stores, {**cached["meta"], "from_cache": True}

        items: list[dict[str, Any]] = []
        truncated = False
        page = 1
        total_count = 0
        while page <= self.settings.max_pages:
            try:
                payload = self._request_page(cache_lat, cache_lon, radius_m, page)
            except NoDataError:
                total_count = len(items)
                break
            page_items, total_count = _extract_items(payload)
            items.extend(page_items)
            if len(items) >= total_count or not page_items:
                break
            page += 1

        if len(items) < total_count:
            truncated = True

        meta = {
            "total_count": total_count,
            "fetched": len(items),
            "truncated": truncated,
            "radius_m": radius_m,
            "reference_date": reference_date_of(items),
            "from_cache": False,
        }
        if use_cache:
            _write_cache(path, {"items": items, "meta": meta})

        stores = [s for s in (to_store(i) for i in items) if s]
        return stores, meta

    def stores_in_radius_with_fallback(
        self,
        lat: float,
        lon: float,
        candidates: tuple[int, ...],
        grid_m: int | None = None,
    ) -> tuple[list[Store], dict[str, Any]]:
        last_error: SbizApiError | None = None
        for radius_m in candidates:
            try:
                return self.stores_in_radius(lat, lon, radius_m, grid_m=grid_m)
            except RadiusRejectedError as exc:
                last_error = exc
                continue
            except SbizApiError as exc:
                last_error = exc
                if "radius" in exc.message.lower() or "반경" in exc.message:
                    continue
                raise
        raise last_error or SbizApiError("NO_RADIUS", "사용 가능한 반경을 찾지 못했습니다.")
