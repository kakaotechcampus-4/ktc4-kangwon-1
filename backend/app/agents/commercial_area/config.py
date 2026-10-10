"""상권 경쟁 분석에 쓰는 설정값입니다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import BACKEND_DIR, load_environment

# 기존 CLI 가져오기 경로를 유지합니다.
load_dotenv_if_present = load_environment

PACKAGE_DIR = Path(__file__).resolve().parent

SBIZ_BASE_URL = "https://apis.data.go.kr/B553077/api/open/sdsc2"
SBIZ_RADIUS_OPERATION = "storeListInRadius"
SBIZ_DISTRICT_OPERATION = "storeListInDong"
FTC_BRAND_BASE_URL = "https://apis.data.go.kr/1130000/FftcBrandFrcsStatsService"
FTC_BRAND_OPERATION = "getBrandFrcsStats"

RESTAURANT_MAJOR_NAMES = ("음식점업", "음식", "음식점")


@dataclass(frozen=True)
class Settings:
    analysis_radius_m: int = 500
    lq_radius_candidates: tuple[int, ...] = (2000, 1500, 1000)
    # 결정 에이전트가 data 를 통째로 프롬프트에 넣는데(decision/agent.py 가 자르지 않는다)
    # by_radius 가 전체의 44%라 빈 응답이 났다. 단계와 순위 길이를 줄여 크기를 맞춘다.
    breakdown_radii: tuple[int, ...] = (50, 200, 500)
    rank_size: int = 5
    min_count_for_specialization: int = 5

    page_size: int = 1000
    max_pages: int = 60
    max_concurrency: int = 4
    request_timeout_s: float = 15.0
    max_retries: int = 2
    retry_backoff_s: float = 1.5

    cache_dir: Path = BACKEND_DIR / "cache"
    cache_ttl_hours: int = 24 * 7
    district_cache_ttl_hours: int = 24 * 90
    district_max_pages: int = 120
    lq_cache_grid_m: int = 250

    sbiz_service_key: str | None = None
    ftc_service_key: str | None = None
    ftc_year: str = "2025"
    geocoding_api_key: str | None = None

    @classmethod
    def from_env(cls, **overrides) -> Settings:
        env_values: dict[str, Any] = {
            "sbiz_service_key": os.environ.get("COMMERCIAL_AREA_API_KEY"),
            "ftc_service_key": os.environ.get("FRANCHISE_API_KEY"),
            "geocoding_api_key": os.environ.get("GEOCODING_API_KEY"),
        }
        for name, key in (("max_concurrency", "SBIZ_MAX_CONCURRENCY"),):
            raw = os.environ.get(key)
            if raw:
                env_values[name] = int(raw)
        env_values.update(overrides)
        return cls(**{k: v for k, v in env_values.items() if v is not None})
