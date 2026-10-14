"""선택한 모델 호출만 정제해 녹화하고 원천·도구 실행은 그대로 재생합니다."""

import asyncio
import json
import re
from copy import deepcopy
from pathlib import Path

from openai.types.chat import ChatCompletionMessage
from pydantic import BaseModel

from app.canonical import canonical_json
from app.concurrency import run_in_thread
from app.llm.budget import BudgetExceeded
from app.llm.client import LLMHTTPError, LLMResponseError
from app.storage.scrub import env_secrets, scrub

_IDENTIFIER = re.compile(
    r"^(?P<prefix>(?:request|snapshot|fact|tc|consult|score|question|report|map|f|s|sc|ss)_)?"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _serialize(value):
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else deepcopy(value)


def _load(path):
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError("녹화 파일은 호출 객체 배열이어야 합니다.")
    return entries


class CallRecording:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = asyncio.Lock()

    async def record(self, role, messages, value, receipt, elapsed_ms, error=None):
        serialized = _serialize(value)
        raw = _serialize(receipt.get("raw_response") or serialized)
        raw_message = (
            (raw.get("choices") or [{}])[0].get("message", {}) if isinstance(raw, dict) else {}
        )
        failure = (
            {
                "type": type(error).__name__,
                "code": getattr(error, "code", type(error).__name__),
                "diagnostics": getattr(error, "diagnostics", {}),
            }
            if error is not None
            else None
        )
        entry = {
            "role": role,
            "messages": _serialize(receipt.get("sent_messages", messages)),
            "raw_response": raw,
            "value": serialized,
            "tool_calls": serialized.get("tool_calls")
            if isinstance(serialized, dict)
            else raw_message.get("tool_calls"),
            "usage": _serialize(receipt.get("usage")),
            "model": receipt.get("model"),
            "elapsed_ms": elapsed_ms,
            "error_code": failure["code"] if failure else None,
            "error": failure,
        }
        secrets = env_secrets()
        async with self._lock:
            await run_in_thread(self._append, scrub(entry, secrets))

    def _append(self, entry):
        entries = _load(self.path) if self.path.exists() else []
        entries.append(entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(canonical_json(entries), encoding="utf-8")
        temporary.replace(self.path)


def _json_body(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _map_ids(recorded, current, identifiers):
    if isinstance(recorded, dict) and isinstance(current, dict):
        for key in recorded.keys() & current.keys():
            _map_ids(recorded[key], current[key], identifiers)
    elif isinstance(recorded, list) and isinstance(current, list):
        if all(
            isinstance(v, str) and _IDENTIFIER.fullmatch(v) for v in [*recorded, *current]
        ) and set(recorded) == set(current):
            for value in recorded:
                _map_ids(value, value, identifiers)
            return
        for old, new in zip(recorded, current, strict=False):
            _map_ids(old, new, identifiers)
    elif isinstance(recorded, str) and isinstance(current, str):
        old, new = _IDENTIFIER.fullmatch(recorded), _IDENTIFIER.fullmatch(current)
        if old and new and old["prefix"] == new["prefix"]:
            if recorded in identifiers and identifiers[recorded] != current:
                raise ValueError("녹화 식별자가 서로 다른 재생 식별자에 대응합니다.")
            identifiers[recorded] = current
        else:
            old_body, new_body = _json_body(recorded), _json_body(current)
            if old_body is not None and new_body is not None:
                _map_ids(old_body, new_body, identifiers)


def _remap(value, identifiers):
    if isinstance(value, dict):
        return {identifiers.get(k, k): _remap(v, identifiers) for k, v in value.items()}
    if isinstance(value, list):
        return [_remap(v, identifiers) for v in value]
    if isinstance(value, str):
        if value in identifiers:
            return identifiers[value]
        body = _json_body(value)
        if body is not None:
            remapped = _remap(body, identifiers)
            if remapped != body:
                return canonical_json(remapped)
    return value


def _raise_recorded(failure):
    kind, code = failure["type"], failure["code"]
    diagnostics = failure.get("diagnostics") or {}
    if kind == "LLMResponseError":
        raise LLMResponseError(code, **diagnostics)
    if kind == "LLMHTTPError":
        raise LLMHTTPError(
            diagnostics["http_status"],
            {"error": {"code": diagnostics["provider_code"], "param": diagnostics["parameter"]}},
        )
    if kind == "BudgetExceeded":
        raise BudgetExceeded()
    if kind in {"TimeoutError", "CancelledError"}:
        raise TimeoutError()
    raise RuntimeError(f"녹화된 모델 오류: {code}")


class ReplayGenerate:
    def __init__(self, recording_path=None, *, entries=None):
        if isinstance(recording_path, list) and entries is None:
            entries, recording_path = recording_path, None
        if (recording_path is None) == (entries is None):
            raise ValueError("녹화 경로나 호출 배열 중 하나가 필요합니다.")
        self.path = Path(recording_path) if recording_path is not None else None
        self.entries = deepcopy(entries)
        self.position = 0
        self.mapping = {}

    async def __call__(self, messages, definitions, settings, receipt):
        if self.entries is None:
            self.entries = await asyncio.to_thread(_load, self.path)
        if self.position >= len(self.entries):
            raise ValueError("녹화된 모델 호출을 모두 재생했습니다.")
        entry = self.entries[self.position]
        self.position += 1
        if entry.get("role") not in {"decision", "advisor"}:
            raise ValueError("녹화 호출의 역할이 올바르지 않습니다.")
        if entry["role"] != ("decision" if definitions is not None else "advisor"):
            raise ValueError("녹화 호출과 재생 역할의 순서가 다릅니다.")
        _map_ids(entry["messages"], messages, self.mapping)
        receipt.update(model=entry.get("model"), usage=deepcopy(entry.get("usage")))
        receipt["replay_elapsed_ms"] = entry.get("elapsed_ms", 0)
        if receipt.get("_record_raw"):
            receipt["raw_response"] = _remap(entry.get("raw_response"), self.mapping)
            receipt["sent_messages"] = deepcopy(messages)
        if entry.get("error"):
            _raise_recorded(entry["error"])
        value = _remap(entry["value"], self.mapping)
        return ChatCompletionMessage.model_validate(value) if entry["role"] == "decision" else value
