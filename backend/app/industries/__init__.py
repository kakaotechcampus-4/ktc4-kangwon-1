"""팀 공통 업종 어휘 — 소상공인 상권업종 중분류 75종.

세 에이전트가 같은 업종을 가리킬 코드가 없어서 만들었다. 경쟁업체는 중분류 코드(`I201`),
개폐업은 자체 정수 1~70, 결정은 자유 문자열을 쓰고 있었고, 그래서 같은 한식이
`한식음식점` / `한식 음식점업` / `중식`으로 갈려 있었다.

이 어휘가 기준이고, 서울시 생활밀접업종과 개폐업 70종은 여기로 접힌다.

    from app.industries import INDUSTRIES, SEOUL_TO_INDUSTRY
    from app.industries import lookup

원본은 `data/*.csv`이고 `catalog.py`는 **자동 생성물**이다. 고치는 법은 README.md 참고.
"""

from __future__ import annotations

from pathlib import Path

from .models import Industry

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"

MASTER_PATH = DATA_DIR / "industries.csv"
SEOUL_LINK_PATH = DATA_DIR / "seoul_to_industry.csv"
LEGACY70_LINK_PATH = DATA_DIR / "legacy70_to_industry.csv"
# 개폐업 `industry_master.json` 과 같은 모양으로 내보내는 생성물.
MASTER_JSON_PATH = DATA_DIR / "industry_master.json"

__all__ = [
    "DATA_DIR",
    "LEGACY70_LINK_PATH",
    "MASTER_JSON_PATH",
    "MASTER_PATH",
    "PACKAGE_DIR",
    "SEOUL_LINK_PATH",
    "Industry",
]
