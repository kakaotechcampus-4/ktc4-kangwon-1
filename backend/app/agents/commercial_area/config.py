"""상권 경쟁 분석에 쓰는 설정값입니다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parents[3]

SBIZ_BASE_URL = "http://apis.data.go.kr/B553077/api/open/sdsc2"
SBIZ_RADIUS_OPERATION = "storeListInRadius"
FTC_BRAND_BASE_URL = "http://apis.data.go.kr/1130000/FftcBrandFrcsStatsService"
FTC_BRAND_OPERATION = "getBrandFrcsStats"

KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

RESTAURANT_MAJOR_NAMES = ("음식점업", "음식", "음식점")


@dataclass(frozen=True)
class Settings:
    analysis_radius_m: int = 500
    lq_radius_candidates: tuple[int, ...] = (2000, 1500, 1000)
    breakdown_radii: tuple[int, ...] = (50, 100, 200, 300, 500)
    rank_size: int = 10
    min_count_for_specialization: int = 5

    page_size: int = 1000
    max_pages: int = 60
    request_timeout_s: float = 15.0
    max_retries: int = 2
    retry_backoff_s: float = 1.5

    cache_dir: Path = BACKEND_DIR / "cache"
    cache_ttl_hours: int = 24 * 7
    lq_cache_grid_m: int = 250

    upjong_master_path: Path = PACKAGE_DIR / "data" / "upjong_codes.csv"

    sbiz_service_key: str | None = None
    ftc_service_key: str | None = None
    ftc_year: str = "2024"
    geocoding_api_key: str | None = None
    geocoder: str = "auto"
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_max_tokens: int = 8192
    llm_timeout_s: float = 120.0

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        env_values = {
            "sbiz_service_key": os.environ.get("COMMERCIAL_AREA_API_KEY"),
            "ftc_service_key": os.environ.get("FRANCHISE_API_KEY"),
            "geocoding_api_key": os.environ.get("GEOCODING_API_KEY"),
            "geocoder": os.environ.get("GEOCODER"),
            "llm_model": os.environ.get("ELICE_MODEL"),
            "llm_base_url": os.environ.get("ELICE_BASE_URL"),
            "llm_api_key": os.environ.get("ELICE_API_KEY"),
        }
        for name, key in (
            ("analysis_radius_m", "ANALYSIS_RADIUS_M"),
            ("llm_max_tokens", "LLM_MAX_TOKENS"),
        ):
            raw = os.environ.get(key)
            if raw:
                env_values[name] = int(raw)
        timeout = os.environ.get("LLM_TIMEOUT_SECONDS")
        if timeout:
            env_values["llm_timeout_s"] = float(timeout)
        env_values.update(overrides)
        return cls(**{k: v for k, v in env_values.items() if v is not None})


def load_dotenv_if_present() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in (BACKEND_DIR / ".env", Path.cwd() / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)
