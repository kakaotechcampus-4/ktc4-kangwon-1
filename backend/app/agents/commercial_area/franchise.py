"""공정거래위원회 브랜드 목록으로 프랜차이즈 여부를 판정합니다."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

from .config import FTC_BRAND_BASE_URL, FTC_BRAND_OPERATION, Settings
from .schemas import Franchise, FranchiseByMiddle, MiddleCategory, Store

BRAND_CACHE_NAME = "ftc_brands.json"
MIN_BRAND_LENGTH = 2
NORMALIZE_PATTERN = re.compile(r"[\s\(\)\[\]\-_.,'\"·&]+")
BRANCH_SUFFIX_PATTERN = re.compile(r"(점|지점|본점|직영점)$")


def normalize_name(value: str) -> str:
    text = NORMALIZE_PATTERN.sub("", value or "").lower()
    return BRANCH_SUFFIX_PATTERN.sub("", text)


def brand_cache_path(settings: Settings) -> Path:
    return settings.cache_dir / BRAND_CACHE_NAME


def load_cached_brands(settings: Settings) -> list[str] | None:
    path = brand_cache_path(settings)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(payload, dict):
        payload = payload.get("brands")
    if not isinstance(payload, list):
        return None
    return [str(name) for name in payload if str(name).strip()]


def save_brands(settings: Settings, brands: Sequence[str]) -> None:
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    path = brand_cache_path(settings)
    try:
        path.write_text(
            json.dumps({"brands": sorted(set(brands))}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


async def fetch_brands(settings: Settings, max_pages: int = 30) -> list[str]:
    if not settings.ftc_service_key:
        raise RuntimeError("FTC_SERVICE_KEY가 설정되지 않았습니다.")
    url = f"{FTC_BRAND_BASE_URL}/{FTC_BRAND_OPERATION}"
    brands: list[str] = []
    async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
        for page in range(1, max_pages + 1):
            response = await client.get(
                url,
                params={
                    "serviceKey": settings.ftc_service_key,
                    "pageNo": page,
                    "numOfRows": 1000,
                    "resultType": "json",
                    "yr": settings.ftc_year,
                },
            )
            response.raise_for_status()
            payload: Any = response.json()
            items = _brand_items(payload)
            if not items:
                break
            for item in items:
                name = str(item.get("brandNm") or item.get("brand_nm") or "").strip()
                if name:
                    brands.append(name)
    return brands


def _brand_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("items", "item", "body", "response", "data"):
            if key in payload:
                return _brand_items(payload[key])
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


async def load_brands(settings: Settings) -> list[str] | None:
    cached = load_cached_brands(settings)
    if cached:
        return cached
    if not settings.ftc_service_key:
        return None
    try:
        brands = await fetch_brands(settings)
    except (httpx.HTTPError, RuntimeError, json.JSONDecodeError):
        return None
    if not brands:
        return None
    save_brands(settings, brands)
    return brands


def is_franchise(store: Store, normalized_brands: set[str]) -> bool:
    candidate = normalize_name(store.name)
    if len(candidate) < MIN_BRAND_LENGTH:
        return False
    if candidate in normalized_brands:
        return True
    return any(brand in candidate for brand in normalized_brands if len(brand) >= 3)


def build_franchise(
    stores: Sequence[Store],
    brands: Sequence[str],
    middle_rows: Sequence[MiddleCategory],
) -> Franchise:
    normalized_brands = {
        normalized
        for normalized in (normalize_name(b) for b in brands)
        if len(normalized) >= MIN_BRAND_LENGTH
    }
    matched = [s for s in stores if is_franchise(s, normalized_brands)]
    counts = Counter(s.middle_code for s in matched)
    totals = {row.code: row.count for row in middle_rows}
    names = {row.code: row.name for row in middle_rows}

    by_middle = [
        FranchiseByMiddle(
            code=code,
            name=names.get(code, code),
            count=count,
            ratio=round(count / totals[code], 4) if totals.get(code) else 0.0,
        )
        for code, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    total = len(stores)
    return Franchise(
        count=len(matched),
        ratio=round(len(matched) / total, 4) if total else 0.0,
        by_middle=by_middle,
        method="brand_name_match",
        confidence="low",
    )
