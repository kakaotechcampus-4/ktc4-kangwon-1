"""질문 업종과 원본 분류 쌍의 동종 여부를 한 번에 판단합니다."""

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
from typing import Any

from app.config import BACKEND_DIR
from app.llm.budget import BudgetStorageError
from app.llm.client import complete_json
from app.llm.config import LLMSettings
from app.schemas import MatchStatus, Schema, Text

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
                        item = MatchJudgement.model_validate_json(row[0])
                    except ValueError:
                        continue
                    if item.status in {"same", "different"}:
                        result[key] = item
            return result
    except (OSError, sqlite3.Error):
        return {}


class MatchJudgement(Schema):
    status: MatchStatus
    reason: Text


async def judge_matches(
    pairs: dict[str, dict],
    *,
    generate: GenerateMapping | None = None,
    settings: LLMSettings | None = None,
    cache_path: Path | None = None,
) -> dict[str, MatchJudgement]:
    if not pairs:
        return {}
    prompt = await asyncio.to_thread(files(__package__).joinpath("prompt.md").read_text, "utf-8")
    settings = settings or LLMSettings.from_env("MAP_MAPPING")
    # 주입한 대역은 명시적으로 지정한 임시 캐시만 사용합니다.
    if cache_path is None and generate is None:
        cache_path = BACKEND_DIR / "cache" / "map_mappings.sqlite3"
    keys = {
        key: hashlib.sha256(
            json.dumps(
                [value, prompt, settings.model, settings.base_url],
                ensure_ascii=False,
                sort_keys=True,
            ).encode()
        ).hexdigest()
        for key, value in pairs.items()
        if not value.get("place_names")
    }
    cached = await asyncio.to_thread(_cache, cache_path, keys) if cache_path else {}
    pending = {key: value for key, value in pairs.items() if key not in cached}
    if not pending:
        return cached
    raw = json.dumps(
        {
            "pairs": pending,
            "schema": MatchJudgement.model_json_schema(),
        },
        ensure_ascii=False,
    )
    try:
        result = generate(prompt, raw) if generate else complete_json(prompt, raw, settings)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, dict) or set(result) != set(pending):
            raise ValueError("입력 쌍과 동종 판단 응답 항목이 다릅니다.")
        validated = {key: MatchJudgement.model_validate(value) for key, value in result.items()}
    except BudgetStorageError:
        raise
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
                if value.status in {"same", "different"} and key in keys
            },
        )
    return cached | validated
