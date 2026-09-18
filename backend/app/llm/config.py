"""요청별 불변 설정. 인증 누락은 실제 호출 경계에서 확인합니다."""

import math
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMSettings:
    model: str | None = None
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None
    max_tokens: int | None = 8192
    timeout_seconds: float = 120.0
    reasoning_effort: str | None = None

    def __post_init__(self) -> None:
        if (
            self.max_tokens is not None
            and (type(self.max_tokens) is not int or self.max_tokens <= 0)
        ) or (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("응답 길이와 대기 시간은 유한한 양수로 설정해 주세요.")

    @classmethod
    def from_env(cls, agent: str, **overrides: Any) -> "LLMSettings":
        values: dict[str, Any] = {}
        for name, suffix, legacy in (
            ("model", "MODEL", "ELICE_MODEL"),
            ("api_key", "API_KEY", "ELICE_API_KEY"),
            ("base_url", "BASE_URL", "ELICE_BASE_URL"),
            ("max_tokens", "MAX_TOKENS", "LLM_MAX_TOKENS"),
            ("timeout_seconds", "TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS"),
            ("reasoning_effort", "REASONING_EFFORT", "LLM_REASONING_EFFORT"),
        ):
            if name in overrides:
                values[name] = overrides[name]
                continue
            raw = (
                os.getenv(f"{agent.upper()}_LLM_{suffix}", "").strip()
                or os.getenv(legacy, "").strip()
            )
            if not raw:
                continue
            try:
                values[name] = (
                    int(raw)
                    if name == "max_tokens"
                    else float(raw)
                    if name == "timeout_seconds"
                    else raw
                )
            except ValueError:
                raise ValueError("응답 길이와 대기 시간은 유한한 양수로 설정해 주세요.") from None
        return cls(**values)

    def require_credentials(self) -> None:
        for value, name in (
            (self.model, "ELICE_MODEL"),
            (self.api_key, "ELICE_API_KEY"),
            (self.base_url, "ELICE_BASE_URL"),
        ):
            if not value or not value.strip():
                raise ValueError(f"{name} 또는 에이전트별 LLM 설정을 입력해 주세요.")
