"""유동인구 분석에 쓰는 설정값입니다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parents[3]

SEOUL_OPEN_API_BASE = "http://openapi.seoul.go.kr:8088"

# 2026-09-07 실호출로 확인된 서비스명. 데이터셋이 개편되면 각 페이지의 "Open API" 탭에서 재확인.
FLPOP_SERVICE = "VwsmTrdarFlpopQq"  # 상권분석서비스(길단위인구-상권) OA-15568
TRDAR_AREA_SERVICE = "TbgisTrdarRelm"  # 상권분석서비스(영역-상권) OA-15560


@dataclass(frozen=True)
class Settings:
    analysis_radius_m: int = 500

    page_size: int = 1000
    trdar_area_max_pages: int = 20
    flpop_max_pages: int = 5
    quarter_probe_limit: int = 12  # 최신 분기를 찾아 거꾸로 살펴볼 분기 수(3년)
    request_timeout_s: float = 15.0

    # 추세에 쓸 분기 수 — 최신 분기 + 최대 3분기 전까지(2026Q2 기준 2025Q3~2026Q2).
    # 원본은 2021Q1 부터 22개 분기가 있지만 리포트에 필요한 건 최근 흐름뿐이다.
    trend_quarters: int = 4

    # 분석 반경(500m) **안쪽을** 나눠 보는 지점들(m). 반경을 넓히는 게 아니라 쪼개는 것이라
    # 마지막 값이 analysis_radius_m 과 같다. 전부 로컬 면적 안분이라 API 호출은 늘지 않는다.
    radius_profile_m: tuple[int, ...] = (50, 100, 200, 300, 400, 500)

    base_url: str = SEOUL_OPEN_API_BASE
    flpop_service: str = FLPOP_SERVICE
    trdar_area_service: str = TRDAR_AREA_SERVICE

    api_key: str | None = None

    @classmethod
    def from_env(cls, **overrides: Any) -> Settings:
        env_values: dict[str, Any] = {
            "api_key": os.environ.get("FLOATING_POPULATION_API_KEY"),
            "base_url": os.environ.get("SEOUL_OPEN_API_BASE"),
            "flpop_service": os.environ.get("SEOUL_FLPOP_SERVICE"),
            "trdar_area_service": os.environ.get("SEOUL_TRDAR_AREA_SERVICE"),
        }
        radius = os.environ.get("ANALYSIS_RADIUS_M")
        if radius:
            env_values["analysis_radius_m"] = int(radius)
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
