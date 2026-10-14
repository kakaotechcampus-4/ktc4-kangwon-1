"""삭제 대기 중인 옛 마이그레이션 함수만 검증하는 fixture 진입점입니다."""

import sqlite3
from contextlib import closing

from app.db.connection import SCHEMA_VERSION
from app.db.connection import initialize as current_initialize


def initialize(path):
    # 운영 초기화는 구 DB를 거절합니다. 이 시험 복사본만 옛 함수 검증에 사용합니다.
    if path.exists():
        with closing(sqlite3.connect(path)) as db:
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return current_initialize(path)
