"""카카오 지도 조회에 쓰는 설정값"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.config import load_environment

# 기존 CLI 가져오기 경로 유지함
load_dotenv_if_present = load_environment

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_CATEGORY_URL = "https://dapi.kakao.com/v2/local/search/category.json"

# 카카오가 받아주는 반경 상한. 넘기면 400 돌아옴
MAX_RADIUS_M = 20_000


@dataclass(frozen=True)
class Settings:
    # 주소 변환(address.py)이랑 같은 카카오 REST 키 씀. 키를 두 개 둘 이유가 없음
    api_key: str | None = field(default=None, repr=False)
    request_timeout_s: float = 15.0
    max_retries: int = 2
    retry_backoff_s: float = 1.5
    # 검색어 여러 개 동시에 던질 때 상한. 429 피하려고 낮게 잡음
    max_concurrency: int = 4
    # 최근접·브랜드 뽑을 표본 크기
    # 개수(meta.total_count)는 이 값이랑 무관하게 전수라서 여기 키울 이유 없음
    sample_size: int = 5

    @classmethod
    def from_env(cls) -> Settings:
        values: dict[str, object] = {"api_key": os.environ.get("GEOCODING_API_KEY")}
        raw = os.environ.get("MAP_ANALYSIS_MAX_CONCURRENCY")
        if raw:
            values["max_concurrency"] = int(raw)
        return cls(**{k: v for k, v in values.items() if v is not None})  # type: ignore[arg-type]
