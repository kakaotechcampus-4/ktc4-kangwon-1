"""고유 원본 분류를 공통 업종에 한 번만 매핑합니다."""

import inspect
import json
from collections.abc import Awaitable, Callable
from importlib.resources import files
from typing import Any, Literal, Self

from pydantic import model_validator

from app.industries.catalog import INDUSTRIES
from app.llm.client import complete_json
from app.llm.config import LLMSettings
from app.schemas import Schema, Text

GenerateMapping = Callable[[str, str], Awaitable[Any] | Any]


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
) -> dict[str, CategoryMapping]:
    if not categories:
        return {}
    prompt = files(__package__).joinpath("prompt.md").read_text("utf-8")
    raw = json.dumps(
        {
            "categories": categories,
            "industries": INDUSTRIES,
            "schema": CategoryMapping.model_json_schema(),
        },
        ensure_ascii=False,
    )
    result = (
        generate(prompt, raw)
        if generate
        else complete_json(prompt, raw, settings or LLMSettings.from_env("MAP_MAPPING"))
    )
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, dict) or set(result) != set(categories):
        raise ValueError("원본 분류와 매핑 응답 항목이 다릅니다.")
    return {key: CategoryMapping.model_validate(value) for key, value in result.items()}
