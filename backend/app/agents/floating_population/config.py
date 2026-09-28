"""유동인구 분석에 쓰는 설정값입니다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import BACKEND_DIR as BACKEND_DIR
from app.config import load_environment

# 기존 CLI 가져오기 경로를 유지합니다.
load_dotenv_if_present = load_environment

PACKAGE_DIR = Path(__file__).resolve().parent

SEOUL_OPEN_API_BASE = "http://openapi.seoul.go.kr:8088"

# 2026-09-07 실호출로 확인된 서비스명. 데이터셋이 개편되면 각 페이지의 "Open API" 탭에서 재확인.
FLPOP_SERVICE = "VwsmTrdarFlpopQq"  # 상권분석서비스(길단위인구-상권) OA-15568
TRDAR_AREA_SERVICE = "TbgisTrdarRelm"  # 상권분석서비스(영역-상권) OA-15560
RESIDENT_SERVICE = "VwsmTrdarRepopQq"  # 상권분석서비스(상주인구-상권) OA-15584
WORKER_SERVICE = "VwsmTrdarWrcPopltnQq"  # 상권분석서비스(직장인구-상권) OA-15569


@dataclass(frozen=True)
class Settings:
    # 에이전트는 이 값이 아니라 `AnalysisTask.radius_m` 을 쓴다(사용자가 고른 반경).
    # 예제 스크립트가 넘기는 인자라 남겨 둔다.
    analysis_radius_m: int = 500

    page_size: int = 1000
    trdar_area_max_pages: int = 20
    flpop_max_pages: int = 5
    # 주거·직장인구 스냅샷 생성용(에이전트는 API 를 부르지 않는다). 분기 필터가 먹지 않아
    # 22개 분기 전량(약 3.6만 행)을 받는다. 한꺼번에 보내면 서울시 API 가 오류 응답을 주므로
    # 동시 요청을 묶고 페이지마다 재시도한다.
    page_concurrency: int = 8
    page_retries: int = 2
    quarter_probe_limit: int = 12  # 최신 분기를 찾아 거꾸로 살펴볼 분기 수(3년)
    request_timeout_s: float = 15.0

    # 추세에 쓸 분기 수 — 최신 분기 + 최대 3분기 전까지(2026Q2 기준 2025Q3~2026Q2).
    # 원본은 2021Q1 부터 22개 분기가 있지만 리포트에 필요한 건 최근 흐름뿐이다.
    trend_quarters: int = 4

    # 분석 반경 **안쪽을** 나눠 보는 지점들(m). 반경을 넓히는 게 아니라 쪼개는 것이라 분석
    # 반경보다 큰 값은 버리고 분석 반경 자체를 마지막 점으로 붙인다(agent.py).
    # 전부 로컬 면적 안분이라 API 호출은 늘지 않는다.
    radius_profile_m: tuple[int, ...] = (50, 100, 200, 300, 400, 500)

    base_url: str = SEOUL_OPEN_API_BASE
    flpop_service: str = FLPOP_SERVICE
    trdar_area_service: str = TRDAR_AREA_SERVICE
    resident_service: str = RESIDENT_SERVICE
    worker_service: str = WORKER_SERVICE

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
