"""근거 값을 문장의 자리표시자에 채웁니다."""

import re
from collections.abc import Mapping
from typing import Any

from .findings import _allowed_units
from .pointer import parse_pointer as pointer_segments
from .pointer import resolve_pointer

_PLACEHOLDER = re.compile(r"\{(\d+)\}")
_UNIT = re.compile(r"\s*(명/일|개소|명|개|원|점|배|미터|m|%)")
_SCALE = re.compile(r"\s*[만억천]")
_DIGITS = re.compile(r"\d+")


class CitationError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _dict_keys(data: Any, path: str) -> list[str]:
    keys = []
    for key in pointer_segments(path):
        if isinstance(data, dict) and key in data:
            keys.append(key)
            data = data[key]
        elif isinstance(data, list) and key.isdigit() and int(key) < len(data):
            data = data[int(key)]
        else:
            break
    return keys


def render_cited(
    text: str,
    refs: list[tuple[str, str]],
    sources: Mapping[str, Any],
    *,
    map_radii: set[int] | None = None,
) -> str:
    labels = {
        digits
        for agent_id, path in refs
        for key in _dict_keys(sources.get(agent_id, {}), path)
        for digits in _DIGITS.findall(key)
    }
    uncited = _PLACEHOLDER.sub("", text)
    # 지도 관측 반경은 MapData 밖의 문맥입니다. 장소 거리·건수는 자리표시자로 인용합니다.
    if map_radii and refs and all(agent_id == "map_analysis" for agent_id, _ in refs):
        uncited = re.sub(
            r"(?<![\d.])(\d+)\s*m(?![A-Za-z])",
            lambda m: "" if int(m.group(1)) in map_radii else m.group(0),
            uncited,
        )
    if any(digits not in labels for digits in _DIGITS.findall(uncited)):
        raise CitationError("number_uncited")
    pieces: list[str] = []
    cursor = 0
    for match in _PLACEHOLDER.finditer(text):
        index = int(match.group(1))
        if index >= len(refs):
            raise CitationError("placeholder_out_of_range")
        agent_id, path = refs[index]
        data = sources.get(agent_id, {})
        try:
            value = resolve_pointer(data, path)
        except (KeyError, IndexError, ValueError, TypeError):
            raise CitationError("placeholder_value_invalid") from None
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise CitationError("placeholder_value_invalid")
        if _SCALE.match(text, match.end()):
            raise CitationError("unit_mismatch")
        unit = _UNIT.match(text, match.end())
        allowed = _allowed_units(agent_id, path, data)
        if unit and unit.group(1) not in allowed | ({"명"} if "명/일" in allowed else set()):
            raise CitationError("unit_mismatch")
        pieces.extend(
            [text[cursor : match.start()], value if isinstance(value, str) else f"{value:,}"]
        )
        cursor = match.end()
    return "".join([*pieces, text[cursor:]])
