"""인증이 붙은 API를 시험할 때 쓰는 공용 헬퍼입니다.

진짜 계정을 DB에 만들고 나서 의존성을 끕니다. 가짜 사용자만 주입하면
analysis_owners 의 외래키가 깨집니다.

주의: 이 헬퍼로 모든 인증 시험을 대신하지 마세요. 의존성을 꺼 버리므로
current_user 의 실제 구현이 한 번도 돌지 않습니다. 쿠키로 들어오는 진짜 경로는
tests/test_auth_api.py 가 따로 검증합니다.
"""

from __future__ import annotations

from typing import Any

from app.api.v1.analyses import require_owner
from app.api.v1.deps import current_user, optional_user, require_origin, verified_user
from app.db.connection import initialize
from app.db.repository import users as user_repo
from app.passwords import hash_password

TEST_EMAIL = "tester@example.com"
TEST_PASSWORD = "testpassword1"
ALLOWED_ORIGIN = "http://localhost:3000"


def create_user(
    db_path, *, email: str = TEST_EMAIL, verified: bool = True, name: str = "시험 사용자"
) -> dict[str, Any]:
    """DB에 계정을 하나 만들고 행을 돌려줍니다. 같은 DB에 여러 번 불러도 괜찮습니다."""
    initialize(db_path)
    existing = user_repo.get_user_by_email(email, db_path=db_path)
    if existing is not None:
        return existing
    user_id = user_repo.create_email_user(
        email, hash_password(TEST_PASSWORD), name, db_path=db_path
    )
    if verified:
        user_repo.mark_email_verified(user_id, db_path=db_path)
    user = user_repo.get_user(user_id, db_path=db_path)
    assert user is not None
    return user


def login(app, db_path, *, verified: bool = True, email: str = TEST_EMAIL) -> dict[str, Any]:
    """계정을 만들고 인증·Origin 의존성을 끕니다. 소유자 검사는 그대로 둡니다."""
    user = create_user(db_path, email=email, verified=verified)
    app.dependency_overrides[optional_user] = lambda: user
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[verified_user] = lambda: user
    app.dependency_overrides[require_origin] = lambda: None
    return user


def allow_any_owner(app) -> None:
    """소유자 검사까지 끄고 싶을 때만 씁니다(요청을 직접 만들어 넣는 시험)."""
    app.dependency_overrides[require_owner] = lambda: None
