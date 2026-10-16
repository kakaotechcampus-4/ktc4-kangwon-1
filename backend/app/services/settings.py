"""서버 요청 DB 경로와 동시 작업 수를 시작 시 고정합니다."""

import os
from dataclasses import dataclass
from pathlib import Path

from app.db.connection import resolve_path


@dataclass(frozen=True)
class ExecutionSettings:
    db_path: str | Path | None = None
    max_concurrency: int = 2

    def __post_init__(self):
        if type(self.max_concurrency) is not int or self.max_concurrency < 1:
            raise ValueError("동시 분석 수는 양의 정수여야 합니다.")

    @classmethod
    def from_env(cls):
        return cls(
            db_path=resolve_path(), max_concurrency=int(os.getenv("ANALYSIS_MAX_CONCURRENCY", "2"))
        )
