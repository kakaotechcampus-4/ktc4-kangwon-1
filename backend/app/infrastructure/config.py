"""환경 파일은 서버·CLI 진입점에서 한 번만 읽습니다."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def backend_dir(start: Path) -> Path:
    for parent in start.resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(
        "backend/pyproject.toml을 찾지 못했습니다. backend에서 pip install -e 로 설치하세요."
    )


BACKEND_DIR = backend_dir(Path(__file__))


@dataclass(frozen=True)
class AddressSettings:
    api_key: str | None = field(default=None, repr=False)
    timeout: float = 15.0

    @classmethod
    def from_env(cls) -> "AddressSettings":
        return cls(api_key=os.environ.get("GEOCODING_API_KEY"))


def load_environment() -> None:
    load_dotenv(BACKEND_DIR / ".env", override=False)
