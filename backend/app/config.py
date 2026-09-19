"""환경 파일은 서버·CLI 진입점에서 한 번만 읽습니다."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AddressSettings:
    api_key: str | None = field(default=None, repr=False)
    timeout: float = 15.0

    @classmethod
    def from_env(cls) -> "AddressSettings":
        return cls(api_key=os.environ.get("GEOCODING_API_KEY"))


def load_environment() -> None:
    load_dotenv(BACKEND_DIR / ".env", override=False)
