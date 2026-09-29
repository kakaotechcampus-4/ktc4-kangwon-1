"""고유 원본 분류를 공통 업종에 한 번만 매핑합니다."""

import asyncio
import hashlib
import inspect
import json
import sqlite3
import time
from collections.abc import Awaitable, Callable
from contextlib import closing
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import model_validator

from app.config import BACKEND_DIR
from app.industries.catalog import INDUSTRIES
from app.llm.client import complete_json
from app.llm.config import LLMSettings
from app.schemas import Schema, Text

GenerateMapping = Callable[[str, str], Awaitable[Any] | Any]


def _cache(
    path: Path, keys: dict[str, str], values: dict[str, str] | None = None
) -> dict[str, Any]:
    """캐시 실패는 조회를 막지 않습니다. 모델 검증 결과이며 사람 검수표가 아닙니다."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=5)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS mappings (key TEXT PRIMARY KEY, value TEXT, saved REAL)"
            )
            if values is not None:
                connection.executemany(
                    "INSERT OR REPLACE INTO mappings VALUES (?, ?, ?)",
                    [(keys[key], value, time.time()) for key, value in values.items()],
                )
                connection.execute("DELETE FROM mappings WHERE saved < ?", (time.time() - 604800,))
                return {}
            result = {}
            for key, digest in keys.items():
                row = connection.execute(
                    "SELECT value FROM mappings WHERE key = ? AND saved >= ?",
                    (digest, time.time() - 604800),
                ).fetchone()
                if row:
                    try:
                        item = CategoryMapping.model_validate_json(row[0])
                    except ValueError:
                        continue
                    if item.status == "mapped":
                        result[key] = item
            return result
    except (OSError, sqlite3.Error):
        return {}


class CategoryMapping(Schema):
    status: Literal["mapped", "ambiguous", "unmapped"]
    industry_code: Text | None = None
    reason: Text

    @model_validator(mode="after")
    def check_code(self) -> Self:
        if self.status == "mapped":
            if self.industry_code not in INDUSTRIES:
                raise ValueError("공통 업종 코드가 아닙니다.")
        elif self.industry_code is not None:
            raise ValueError("미확정 분류는 코드를 지정하지 않습니다.")
        return self


async def map_categories(
    categories: dict[str, dict[str, str]],
    *,
    generate: GenerateMapping | None = None,
    settings: LLMSettings | None = None,
    cache_path: Path | None = None,
) -> dict[str, CategoryMapping]:
    if not categories:
        return {}
    prompt = files(__package__).joinpath("prompt.md").read_text("utf-8")
    settings = settings or LLMSettings.from_env("MAP_MAPPING")
    # 주입한 대역은 명시적으로 지정한 임시 캐시만 사용합니다.
    if cache_path is None and generate is None:
        cache_path = BACKEND_DIR / "cache" / "map_mappings.sqlite3"
    keys = {
        key: hashlib.sha256(
            json.dumps(
                [value, INDUSTRIES, prompt, settings.model, settings.base_url],
                ensure_ascii=False,
                sort_keys=True,
            ).encode()
        ).hexdigest()
        for key, value in categories.items()
    }
    cached = await asyncio.to_thread(_cache, cache_path, keys) if cache_path else {}
    pending = {key: value for key, value in categories.items() if key not in cached}
    if not pending:
        return cached
    raw = json.dumps(
        {
            "categories": pending,
            "industries": INDUSTRIES,
            "schema": CategoryMapping.model_json_schema(),
        },
        ensure_ascii=False,
    )
    try:
        result = generate(prompt, raw) if generate else complete_json(prompt, raw, settings)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, dict) or set(result) != set(pending):
            raise ValueError("원본 분류와 매핑 응답 항목이 다릅니다.")
        validated = {key: CategoryMapping.model_validate(value) for key, value in result.items()}
    except (RuntimeError, ValueError):
        if cached:
            return cached
        raise
    if cache_path:
        await asyncio.to_thread(
            _cache,
            cache_path,
            keys,
            {
                key: value.model_dump_json()
                for key, value in validated.items()
                if value.status == "mapped"
            },
        )
    return cached | validated
