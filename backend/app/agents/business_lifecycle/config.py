"""Business Lifecycle 에이전트 설정입니다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parents[2]


@dataclass(frozen=True)
class Settings:
    quarter_count: int = 12
    area_page_size: int = 1000
    area_max_centroid_distance_m: float = 1500.0
    latest_quarter_search_count: int = 12
    request_timeout_s: float = 10.0
    base_quarter_override: str | None = None
    area_code_override: str | None = None
    area_name_override: str | None = None

    @classmethod
    def from_env(cls, **overrides: Any) -> Settings:
        env_values: dict[str, Any] = {
            "base_quarter_override": os.environ.get("BUSINESS_LIFECYCLE_BASE_QUARTER"),
            "area_code_override": os.environ.get("BUSINESS_LIFECYCLE_AREA_CODE"),
            "area_name_override": os.environ.get("BUSINESS_LIFECYCLE_AREA_NAME"),
        }
        for name, key in (
            ("quarter_count", "BUSINESS_LIFECYCLE_QUARTER_COUNT"),
            ("area_page_size", "BUSINESS_LIFECYCLE_AREA_PAGE_SIZE"),
            ("latest_quarter_search_count", "BUSINESS_LIFECYCLE_LATEST_QUARTER_SEARCH_COUNT"),
        ):
            raw = os.environ.get(key)
            if raw:
                env_values[name] = int(raw)
        raw_distance = os.environ.get("BUSINESS_LIFECYCLE_AREA_MAX_DISTANCE_M")
        if raw_distance:
            env_values["area_max_centroid_distance_m"] = float(raw_distance)
        timeout = os.environ.get("BUSINESS_LIFECYCLE_TIMEOUT_SECONDS")
        if timeout:
            env_values["request_timeout_s"] = float(timeout)
        env_values.update(overrides)
        return cls(**{key: value for key, value in env_values.items() if value is not None})


def load_dotenv_if_present() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in (BACKEND_DIR / ".env", Path.cwd() / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)
