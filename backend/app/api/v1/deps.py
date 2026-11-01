"""요청에서 로그인 사용자를 꺼내는 의존성입니다.

전역 미들웨어로 걸지 않습니다. /health 까지 막히면 deploy.sh 의 헬스체크가
60초 안에 200을 못 받아 배포가 전환되지 않고 중단됩니다.
모듈 수준 함수로 두어 테스트가 app.dependency_overrides 로 끌 수 있게 합니다.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from app.services.auth import SESSION_COOKIE_NAME, is_verified, origin_allowed, session_user

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def db_path(request: Request):
    return request.app.state.execution_settings.db_path


async def optional_user(request: Request) -> dict[str, Any] | None:
    return await session_user(request.cookies.get(SESSION_COOKIE_NAME), db_path=db_path(request))


async def current_user(
    user: Annotated[dict[str, Any] | None, Depends(optional_user)],
) -> dict[str, Any]:
    if user is None:
        raise HTTPException(401, "로그인이 필요합니다.")
    return user


async def verified_user(
    user: Annotated[dict[str, Any], Depends(current_user)],
) -> dict[str, Any]:
    """이메일로 가입한 계정은 메일 확인까지 끝나야 분석을 돌릴 수 있습니다."""
    if not is_verified(user):
        raise HTTPException(403, "이메일 확인을 먼저 끝내 주세요.")
    return user


async def require_origin(request: Request) -> None:
    """쿠키 인증이라 쓰기 요청은 Origin 을 한 번 더 봅니다.

    CORSMiddleware 는 브라우저에 알려줄 뿐 요청을 막지 않습니다.
    헤더가 없으면 거부가 기본입니다 — 있으면 허용으로 두면 구멍이 됩니다.
    """
    if request.method not in UNSAFE_METHODS:
        return
    allowed = getattr(request.app.state, "allowed_origins", [])
    if not origin_allowed(request.headers.get("origin"), allowed):
        raise HTTPException(403, "허용되지 않은 출처입니다.")
