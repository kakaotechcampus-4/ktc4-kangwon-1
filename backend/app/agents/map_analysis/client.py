"""카카오 로컬 API 호출만 함. 집계나 판단은 안 함"""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any

import httpx

from .config import KAKAO_CATEGORY_URL, KAKAO_KEYWORD_URL, MAX_RADIUS_M, Settings

RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_RETRY_BACKOFF_S = 1.5
MAX_BACKOFF_S = 30.0


class MapApiError(Exception):
    """카카오 조회 실패. 원문 예외 메시지는 안 담음 — 키가 섞여 나갈 수 있음"""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        return None
    return min(seconds, MAX_BACKOFF_S) if math.isfinite(seconds) and seconds >= 0 else None


def _checked(payload: Any) -> dict[str, Any]:
    """응답 뼈대만 확인함. 값 해석은 부르는 쪽에서 함"""
    if not isinstance(payload, dict):
        raise MapApiError("BAD_RESPONSE", "지도 조회 응답이 객체가 아닙니다.")
    meta, documents = payload.get("meta"), payload.get("documents")
    if not isinstance(meta, dict) or not isinstance(documents, list):
        raise MapApiError("BAD_RESPONSE", "지도 조회 응답 구조가 올바르지 않습니다.")
    # total_count 가 이 도구의 유일한 개수 근거라 없으면 결과를 못 만듦
    if type(meta.get("total_count")) is not int or meta["total_count"] < 0:
        raise MapApiError("BAD_RESPONSE", "지도 조회 응답에 전체 건수가 없습니다.")
    return payload


class PlaceClient:
    """카카오 로컬 API 비동기 클라이언트

    검색어 여러 개를 동시에 던져서 요청 수가 한 번에 늘어남.
    쿼터랑 429 생각해서 동시 요청을 max_concurrency 로 묶음.
    """

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client
        self._owns_client = client is None
        self._gate = asyncio.Semaphore(max(1, settings.max_concurrency))
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
        # 주입받은 클라이언트는 안 닫음. 빌려 쓴 거라 수명은 준 쪽이 정함
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None

    async def __aenter__(self) -> PlaceClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def search_keyword(
        self,
        query: str,
        latitude: float,
        longitude: float,
        radius_m: int,
        *,
        category_group_code: str | None = None,
    ) -> dict[str, Any]:
        """검색어로 찾음. 업종별 개수는 이 경로로만 얻을 수 있음"""
        cleaned = query.strip()
        if not cleaned:
            raise MapApiError("EMPTY_QUERY", "검색어가 비어 있습니다.")
        params: dict[str, Any] = {"query": cleaned}
        # 같은 말이 상호명에도 걸리는 걸 줄임. 커피 216→167, 약국 60→59로 확인함
        if category_group_code:
            params["category_group_code"] = category_group_code
        return await self._get(KAKAO_KEYWORD_URL, params, latitude, longitude, radius_m)

    async def search_category(
        self, category_group_code: str, latitude: float, longitude: float, radius_m: int
    ) -> dict[str, Any]:
        """카카오가 정한 18종 분류로 찾음. 지하철역·학교처럼 검색어가 애매한 거에 씀"""
        code = category_group_code.strip()
        if not code:
            raise MapApiError("EMPTY_QUERY", "분류 코드가 비어 있습니다.")
        return await self._get(
            KAKAO_CATEGORY_URL, {"category_group_code": code}, latitude, longitude, radius_m
        )

    async def _get(
        self,
        url: str,
        query: dict[str, Any],
        latitude: float,
        longitude: float,
        radius_m: int,
    ) -> dict[str, Any]:
        key = self.settings.api_key
        if not isinstance(key, str) or not key.strip():
            raise MapApiError("CONFIG_ERROR", "카카오 REST 키가 설정되지 않았습니다.")
        if type(radius_m) is not int or not 0 < radius_m <= MAX_RADIUS_M:
            raise MapApiError("INVALID_RADIUS", f"반경은 1~{MAX_RADIUS_M}m 사이여야 합니다.")

        params = {
            **query,
            "x": longitude,
            "y": latitude,
            "radius": radius_m,
            "sort": "distance",
            "size": self.settings.sample_size,
        }
        headers = {"Authorization": f"KakaoAK {key.strip()}"}

        backoff = self.settings.retry_backoff_s
        if not math.isfinite(backoff) or backoff < 0:
            backoff = DEFAULT_RETRY_BACKOFF_S
        timed_out = False

        async with self._gate:
            for attempt in range(self.settings.max_retries + 1):
                wait_s = min(backoff * (attempt + 1), MAX_BACKOFF_S)
                try:
                    response = await self._http().get(url, params=params, headers=headers)
                    self.calls_made += 1
                    # 키 문제는 재시도해도 같은 답 옴. 바로 끊음
                    if response.status_code in {401, 403}:
                        raise MapApiError("KAKAO_AUTH", "카카오 REST 키가 거부됐습니다.")
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
                    except (json.JSONDecodeError, ValueError) as exc:
                        raise MapApiError(
                            "BAD_RESPONSE", "지도 조회 응답 형식이 올바르지 않습니다."
                        ) from exc
                    return _checked(payload)
                except MapApiError:
                    raise
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code not in RETRY_STATUS_CODES:
                        raise MapApiError(
                            "UPSTREAM_FAILED", "지도 조회 서비스 연결에 실패했습니다."
                        ) from exc
                    if attempt < self.settings.max_retries:
                        await asyncio.sleep(wait_s)
                        continue
                except httpx.TimeoutException:
                    timed_out = True
                    if attempt < self.settings.max_retries:
                        await asyncio.sleep(wait_s)
                        continue
                except httpx.TransportError:
                    timed_out = False
                    if attempt < self.settings.max_retries:
                        await asyncio.sleep(wait_s)
                        continue

        # 재시도 다 쓴 경우. 마지막 실패가 시간 초과였는지로 코드 가름
        if timed_out:
            raise MapApiError("UPSTREAM_TIMEOUT", "지도 조회 시간이 초과되었습니다.")
        raise MapApiError("UPSTREAM_FAILED", "지도 조회 서비스 연결에 실패했습니다.")
