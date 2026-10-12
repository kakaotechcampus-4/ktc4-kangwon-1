"""JSON Pointer의 이스케이프·해석을 한 곳에서 처리합니다."""

import re
from typing import Any

from pydantic import BaseModel


def escape_pointer(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def parse_pointer(path: str) -> list[str]:
    if not path.startswith("/") or re.search(r"~(?![01])", path):
        raise ValueError("잘못된 근거 경로입니다.")
    return [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]


def resolve_pointer(data: Any, path: str) -> Any:
    """배열 위치를 추정하지 않으며 모델은 선언한 필드만 읽습니다."""
    for key in parse_pointer(path):
        if isinstance(data, dict):
            data = data[key]
        elif isinstance(data, list) and re.fullmatch(r"0|[1-9][0-9]*", key):
            data = data[int(key)]
        elif isinstance(data, BaseModel) and key in type(data).model_fields:
            data = getattr(data, key)
        else:
            raise KeyError(key)
    return data
