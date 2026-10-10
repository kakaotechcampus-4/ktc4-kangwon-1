"""공정거래위원회 브랜드 목록으로 프랜차이즈 여부를 판정합니다."""

from __future__ import annotations

import asyncio
import html
import json
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

from .config import FTC_BRAND_BASE_URL, FTC_BRAND_OPERATION, Settings
from .schemas import Franchise, FranchiseByMiddle, MiddleCategory, Store

MIN_BRAND_LENGTH = 2
NORMALIZE_PATTERN = re.compile(r"[\s\(\)\[\]\-_.,'\"·&]+")
BRANCH_SUFFIX_PATTERN = re.compile(r"(점|지점|본점|직영점)$")
PAREN_PATTERN = re.compile(r"\(([^()]*)\)")
LATIN_RUN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\s&.'\-]*")
CORPORATE_PREFIX_PATTERN = re.compile(r"^\s*(\(주\)|㈜|주식회사|\(유\)|유한회사)\s*")
MIN_PREFIX_ALIAS_LENGTH = 3
LONG_ALIAS_LENGTH = 5


def normalize_name(value: str) -> str:
    text = NORMALIZE_PATTERN.sub("", value or "").lower()
    return BRANCH_SUFFIX_PATTERN.sub("", text)


def brand_keys(brand: str) -> tuple[set[str], set[str]]:
    text = html.unescape(brand or "")
    names = {normalize_name(brand or "")}
    aliases = {
        normalize_name(text),
        normalize_name(PAREN_PATTERN.sub(" ", text)),
        *map(normalize_name, PAREN_PATTERN.findall(text)),
    }
    names = {key for key in names if len(key) >= MIN_BRAND_LENGTH}
    return names, {key for key in aliases if len(key) >= MIN_BRAND_LENGTH} - names


def brand_cache_path(settings: Settings) -> Path:
    # 연도를 파일 이름에 넣는다. 이게 없으면 ftc_year 를 올려도 지난 연도 목록이 그대로 읽히고,
    # franchise.base_year 는 새 연도를 가리켜 실제와 어긋난다.
    return settings.cache_dir / f"ftc_brands_{settings.ftc_year}.json"


def load_cached_brands(settings: Settings) -> list[str] | None:
    path = brand_cache_path(settings)
    try:
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None
    if isinstance(payload, dict):
        payload = payload.get("brands")
    if not isinstance(payload, list):
        return None
    return [str(name) for name in payload if str(name).strip()]


def save_brands(settings: Settings, brands: Sequence[str]) -> None:
    path = brand_cache_path(settings)
    try:
        settings.cache_dir.mkdir(parents=True, exist_ok=True)
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
    cached = await asyncio.to_thread(load_cached_brands, settings)
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
    await asyncio.to_thread(save_brands, settings, brands)
    return brands


def is_franchise(
    store: Store, normalized_brands: set[str], aliases: set[str] | None = None
) -> bool:
    candidate = normalize_name(store.name)
    if len(candidate) < MIN_BRAND_LENGTH:
        return False
    aliases = aliases or set()
    if candidate in normalized_brands or candidate in aliases:
        return True
    if any(brand in candidate for brand in normalized_brands if len(brand) >= 3):
        return True
    if not aliases:
        return False
    body = CORPORATE_PREFIX_PATTERN.sub("", store.name or "").lstrip()
    first_run = LATIN_RUN_PATTERN.match(body)
    if first_run and normalize_name(first_run.group()) in aliases:
        return True
    head = NORMALIZE_PATTERN.sub("", body).lower()
    for size in range(MIN_PREFIX_ALIAS_LENGTH, len(head) + 1):
        alias, rest = head[:size], head[size:]
        if alias.isascii() or alias not in aliases:
            continue
        if size >= LONG_ALIAS_LENGTH or not rest or rest.endswith("점"):
            return True
    return False


def build_franchise(
    stores: Sequence[Store],
    brands: Sequence[str],
    middle_rows: Sequence[MiddleCategory],
    base_year: int | None = None,
) -> Franchise:
    normalized_brands: set[str] = set()
    aliases: set[str] = set()
    for brand in brands:
        brand_names, brand_aliases = brand_keys(brand)
        normalized_brands |= brand_names
        aliases |= brand_aliases
    aliases -= normalized_brands
    matched = [s for s in stores if is_franchise(s, normalized_brands, aliases)]
    totals = {row.code: row.count for row in middle_rows}
    counts = Counter(s.middle_code for s in matched if s.middle_code in totals)
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
    independent = total - len(matched)
    return Franchise(
        count=len(matched),
        ratio=round(len(matched) / total, 4) if total else 0.0,
        # 프랜차이즈가 아닌 나머지. 받는 쪽이 뺄셈하지 않게 명시 필드로 낸다.
        independent_count=independent,
        independent_ratio=round(independent / total, 4) if total else 0.0,
        by_middle=by_middle,
        method="brand_name_match",
        confidence="low",
        base_year=base_year,
    )
