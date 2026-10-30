"""가입·로그인·세션 엔드포인트입니다."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.db.repository import list_user_requests
from app.db.repository import sessions as session_repo
from app.kakao_oauth import KakaoOAuthError, authorize_url
from app.passwords import PasswordPolicyError
from app.services import auth as service
from app.services.auth import (
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SAMESITE,
    AuthError,
    public_user,
    safe_next,
)

from .deps import current_user, db_path, require_origin

EmailText = Annotated[str, AfterValidator(service.normalize_email)]

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["auth"])

# 콜백은 브라우저 최상위 이동이라 실패도 화면으로 돌려보냅니다.
# JSON 401 을 주면 사용자는 날것의 오류 페이지를 보게 됩니다.
_CALLBACK_ERRORS = {
    "INVALID_STATE": "expired",
    "KAKAO_TOKEN_REJECTED": "failed",
    "KAKAO_PROFILE_REJECTED": "failed",
    "KAKAO_UNAVAILABLE": "unavailable",
    "KAKAO_CONFIG_ERROR": "unavailable",
}


class SignupBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailText
    password: str = Field(min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=50)


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailText
    password: str = Field(min_length=1, max_length=128)


class TokenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # 쿼리스트링이 아니라 본문으로 받습니다. access 로그에 토큰이 남지 않습니다.
    token: str = Field(min_length=1, max_length=400)


class ResetBody(TokenBody):
    new_password: str = Field(min_length=1, max_length=128)


class EmailBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailText


def _settings(request: Request):
    state = request.app.state
    return state.auth_settings, state.kakao_settings, state.mail_settings


def _set_session(response: Response, token: str, request: Request) -> None:
    auth, _, _ = _settings(request)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=int(session_repo.SESSION_TTL.total_seconds()),
        httponly=True,
        secure=auth.cookie_secure,
        samesite=SESSION_COOKIE_SAMESITE,
        path="/",
    )


def _clear_session(response: Response, request: Request) -> None:
    auth, _, _ = _settings(request)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        httponly=True,
        secure=auth.cookie_secure,
        samesite=SESSION_COOKIE_SAMESITE,
        path="/",
    )


@router.post("/auth/signup", status_code=201, dependencies=[Depends(require_origin)])
async def signup(body: SignupBody, request: Request, response: Response):
    auth, _, mail = _settings(request)
    try:
        user_id, sent = await service.signup(
            body.email,
            body.password,
            body.display_name,
            db_path=db_path(request),
            mail=mail,
            auth=auth,
        )
    except PasswordPolicyError as exc:
        raise HTTPException(422, str(exc)) from None
    except AuthError as exc:
        raise HTTPException(409, exc.message) from None
    token = await service.login_after_signup(user_id, db_path=db_path(request))
    _set_session(response, token, request)
    return {"user_id": user_id, "verification_sent": sent}


@router.post("/auth/login", dependencies=[Depends(require_origin)])
async def login(body: LoginBody, request: Request, response: Response):
    try:
        token = await service.login(body.email, body.password, db_path=db_path(request))
    except AuthError as exc:
        status = 429 if exc.code == "TOO_MANY_ATTEMPTS" else 401
        raise HTTPException(status, exc.message) from None
    _set_session(response, token, request)
    return {"status": "ok"}


@router.post("/auth/logout", dependencies=[Depends(require_origin)])
async def logout(request: Request, response: Response):
    await service.logout(request.cookies.get(SESSION_COOKIE_NAME), db_path=db_path(request))
    _clear_session(response, request)
    return {"status": "ok"}


@router.get("/auth/me")
async def me(user: Annotated[dict[str, Any], Depends(current_user)]):
    return public_user(user)


@router.delete("/auth/me", dependencies=[Depends(require_origin)])
async def withdraw(
    user: Annotated[dict[str, Any], Depends(current_user)], request: Request, response: Response
):
    await service.withdraw(user["user_id"], db_path=db_path(request))
    _clear_session(response, request)
    return {"status": "ok"}


@router.post("/auth/verify-email", dependencies=[Depends(require_origin)])
async def verify_email(body: TokenBody, request: Request):
    try:
        await service.verify_email(body.token, db_path=db_path(request))
    except AuthError as exc:
        raise HTTPException(400, exc.message) from None
    return {"status": "ok"}


@router.post("/auth/verification/resend", dependencies=[Depends(require_origin)])
async def resend_verification(
    user: Annotated[dict[str, Any], Depends(current_user)], request: Request
):
    auth, _, mail = _settings(request)
    try:
        sent = await service.resend_verification(
            user, db_path=db_path(request), mail=mail, auth=auth
        )
    except AuthError as exc:
        raise HTTPException(409, exc.message) from None
    return {"verification_sent": sent}


@router.post("/auth/password/forgot", dependencies=[Depends(require_origin)])
async def forgot_password(body: EmailBody, request: Request):
    auth, _, mail = _settings(request)
    await service.forgot_password(body.email, db_path=db_path(request), mail=mail, auth=auth)
    # 계정이 있든 없든 같은 응답입니다. 다르면 가입 여부가 새 나갑니다.
    return {"status": "ok"}


@router.post("/auth/password/reset", dependencies=[Depends(require_origin)])
async def reset_password(body: ResetBody, request: Request, response: Response):
    try:
        await service.reset_password(body.token, body.new_password, db_path=db_path(request))
    except PasswordPolicyError as exc:
        raise HTTPException(422, str(exc)) from None
    except AuthError as exc:
        raise HTTPException(400, exc.message) from None
    _clear_session(response, request)
    return {"status": "ok"}


@router.get("/auth/kakao/login")
async def kakao_login(request: Request, next: str = "/"):
    auth, kakao, _ = _settings(request)
    try:
        state = await service.start_kakao_login(safe_next(next), db_path=db_path(request))
        target = authorize_url(kakao, state=state)
    except KakaoOAuthError:
        return RedirectResponse(_login_error(auth.frontend_base_url, "unavailable"), 302)
    return RedirectResponse(target, 302)


@router.get("/auth/kakao/callback")
async def kakao_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    auth, kakao, _ = _settings(request)
    if error:
        # 사용자가 동의 화면에서 취소한 경우입니다.
        return RedirectResponse(_login_error(auth.frontend_base_url, "cancelled"), 302)
    try:
        token, next_path = await service.kakao_callback(
            code, state, db_path=db_path(request), kakao=kakao
        )
    except (AuthError, KakaoOAuthError) as exc:
        reason = _CALLBACK_ERRORS.get(exc.code, "failed")
        return RedirectResponse(_login_error(auth.frontend_base_url, reason), 302)
    redirect = RedirectResponse(f"{auth.frontend_base_url}{next_path}", 302)
    _set_session(redirect, token, request)
    return redirect


def _login_error(frontend: str, reason: str) -> str:
    return f"{frontend}/login?{urlencode({'error': reason})}"


@router.get("/me/analyses")
async def my_analyses(
    user: Annotated[dict[str, Any], Depends(current_user)],
    request: Request,
    limit: int = 20,
    offset: int = 0,
):
    items, total = await asyncio.to_thread(
        list_user_requests, user["user_id"], limit=limit, offset=offset, db_path=db_path(request)
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}
