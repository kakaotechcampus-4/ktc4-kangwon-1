"""팀 공통 서비스 통합 업종 51개.

서비스 업종은 ``SV001``~``SV051`` canonical code를 사용한다. 소상공인
원천 중·소분류 코드와 서울시 생활밀접업종 코드는 CSV 연결표에서만 다룬다.

    from app.industries import INDUSTRIES, SEOUL_TO_INDUSTRY
    from app.industries import lookup

원본은 ``data/*.csv``이고 ``catalog.py``는 자동 생성물이다. 수정 방법은
README.md를 참고한다.
"""

from __future__ import annotations

from pathlib import Path

from .catalog import CATALOG_VERSION, EXPECTED_INDUSTRY_COUNT
from .models import Industry

TAXONOMY: dict[str, str | int] = {
    "id": "service-industry-51",
    "version": CATALOG_VERSION,
    "industry_count": EXPECTED_INDUSTRY_COUNT,
    "seoul_mapping_review": "approved",
    "unreviewed_mapping_count": 0,
}

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"

MASTER_PATH = DATA_DIR / "industries.csv"
PUBLIC_LINK_PATH = DATA_DIR / "public_to_industry.csv"
SEOUL_LINK_PATH = DATA_DIR / "seoul_to_industry.csv"
LEGACY70_LINK_PATH = DATA_DIR / "legacy70_to_industry.csv"

__all__ = [
    "DATA_DIR",
    "LEGACY70_LINK_PATH",
    "MASTER_PATH",
    "PACKAGE_DIR",
    "PUBLIC_LINK_PATH",
    "SEOUL_LINK_PATH",
    "Industry",
]
