"""가입·로그인·세션의 유스케이스입니다. SQLite 접근은 전부 to_thread로 격리합니다."""

from __future__ import annotations

import asyncio
import re
import sqlite3
from typing import Any, Literal
from urllib.parse import urlsplit

from app.config import AuthSettings, KakaoOAuthSettings, MailSettings
from app.db.repository import sessions as session_repo
from app.db.repository import users as user_repo
from app.kakao_oauth import KakaoOAuthError, KakaoProfile, exchange_token, fetch_profile
from app.mailer import MailError, reset_mail, send_mail, verification_mail
from app.passwords import hash_password, validate_password, verify_password

PROVIDER_KAKAO = "kakao"
MAX_EMAIL_LENGTH = 254
# 주소 형식을 엄밀히 따지지 않습니다. 진짜 검증은 "메일을 받아 링크를 눌렀는가"이고,
# 과한 정규식은 멀쩡한 주소를 막습니다. pydantic EmailStr 은 email-validator
# 패키지를 끌고 와서 쓰지 않습니다(신규 의존성 0개 원칙).
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$")
# 쿠키 이름·SameSite·수명은 환경마다 달라질 값이 아니라 상수로 둡니다.
SESSION_COOKIE_NAME = "chaeum_session"
SESSION_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
MAX_NEXT_LENGTH = 200
DEFAULT_NEXT = "/"


class AuthError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


def normalize_email(value: str) -> str:
    """형식을 보고 도메인을 소문자로 접습니다. 사람이 대문자로 적어도 같은 계정입니다."""
    candidate = (value or "").strip()
    if not candidate or len(candidate) > MAX_EMAIL_LENGTH:
        raise ValueError("이메일 주소를 확인해 주세요.")
    if not _EMAIL_PATTERN.match(candidate):
        raise ValueError("이메일 주소를 확인해 주세요.")
    local, _, domain = candidate.partition("@")
    return f"{local}@{domain.lower()}"


def safe_next(path: str | None) -> str:
    """바깥 주소로 튕기지 않게 우리 경로만 허용합니다.

    `//evil.com` 과 `/\\evil.com` 은 브라우저가 스킴 생략 절대주소로 읽습니다.
    """
    if not path or not isinstance(path, str):
        return DEFAULT_NEXT
    candidate = path.strip()
    if len(candidate) > MAX_NEXT_LENGTH or not candidate.startswith("/"):
        return DEFAULT_NEXT
    if candidate.startswith(("//", "/\\")):
        return DEFAULT_NEXT
    return candidate


def is_verified(user: dict[str, Any]) -> bool:
    """메일 인증이 필요한 계정인지 봅니다.

    비밀번호가 없는 계정은 소셜로만 들어온 사람이라 제공자가 신원을 보증합니다.
    """
    return not user.get("password_hash") or bool(user.get("email_verified_at"))


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    """바깥으로 내보낼 필드만 고릅니다. password_hash가 새 나가지 않게 화이트리스트입니다."""
    return {
        "user_id": user["user_id"],
        "email": user.get("email"),
        "display_name": user.get("display_name"),
        "profile_image_url": user.get("profile_image_url"),
        "email_verified": bool(user.get("email_verified_at")),
        "needs_verification": not is_verified(user),
        "created_at": user.get("created_at"),
    }


# ── 이메일 가입·로그인 ──────────────────────────────────────────────────
async def signup(
    email: str,
    password: str,
    display_name: str | None,
    *,
    db_path=None,
    mail: MailSettings,
    auth: AuthSettings,
    client=None,
) -> tuple[str, bool]:
    """계정을 만들고 인증 메일을 보냅니다. 메일 실패해도 계정은 남깁니다."""
    validate_password(password)
    digest = await asyncio.to_thread(hash_password, password)
    try:
        user_id = await asyncio.to_thread(
            user_repo.create_email_user, email, digest, display_name, db_path=db_path
        )
    except sqlite3.IntegrityError as exc:
        raise AuthError("EMAIL_TAKEN", "이미 가입된 이메일입니다.") from exc
    sent = await _send_verification(
        user_id, email, db_path=db_path, mail=mail, auth=auth, client=client
    )
    return user_id, sent


async def _send_verification(
    user_id: str, email: str, *, db_path, mail: MailSettings, auth: AuthSettings, client=None
) -> bool:
    token = await asyncio.to_thread(
        session_repo.create_email_token, user_id, "verify_email", db_path=db_path
    )
    subject, html = verification_mail(f"{auth.frontend_base_url}/verify-email?token={token}")
    try:
        await send_mail(email, subject, html, mail, client=client)
    except MailError:
        # 가입을 되돌리지 않습니다. 같은 주소로 다시 시도할 때 더 꼬입니다.
        return False
    return True


async def login(email: str, password: str, *, db_path=None) -> str:
    """성공하면 세션 원문 토큰을 돌려줍니다."""
    if await asyncio.to_thread(session_repo.too_many_failures, email, db_path=db_path):
        raise AuthError("TOO_MANY_ATTEMPTS", "로그인 시도가 많습니다. 잠시 후 다시 시도해 주세요.")
    user = await asyncio.to_thread(user_repo.get_user_by_email, email, db_path=db_path)
    ok = await asyncio.to_thread(
        verify_password, password, user.get("password_hash") if user else None
    )
    await asyncio.to_thread(session_repo.record_login_attempt, email, succeeded=ok, db_path=db_path)
    if not ok or user is None:
        # 어느 쪽이 틀렸는지 알려주지 않습니다. 가입 여부가 새 나갑니다.
        raise AuthError("INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다.")
    await asyncio.to_thread(user_repo.mark_logged_in, user["user_id"], db_path=db_path)
    await asyncio.to_thread(session_repo.purge_expired, db_path=db_path)
    token, _ = await asyncio.to_thread(
        session_repo.create_session, user["user_id"], db_path=db_path
    )
    return token


async def login_after_signup(user_id: str, *, db_path=None) -> str:
    """가입 직후 바로 로그인시킵니다. 메일 확인은 분석을 돌릴 때 요구합니다.

    확인 전에도 로그인돼 있어야 "인증 메일 다시 보내기" 화면을 보여줄 수 있습니다.
    """
    token, _ = await asyncio.to_thread(session_repo.create_session, user_id, db_path=db_path)
    return token


async def withdraw(user_id: str, *, db_path=None) -> None:
    """탈퇴. 분석 기록은 불변 트리거 때문에 지울 수 없어 소유 연결만 끊습니다.

    카카오 액세스 토큰을 보관하지 않으므로 카카오 쪽 연결 끊기는 하지 못합니다.
    사용자에게는 "우리 서비스에서만 삭제"임을 화면에서 알립니다.
    """
    await asyncio.to_thread(user_repo.delete_user, user_id, db_path=db_path)


async def start_kakao_login(next_path: str, *, db_path=None) -> str:
    return await asyncio.to_thread(session_repo.create_oauth_state, next_path, db_path=db_path)


# ── 메일 인증·비밀번호 재설정 ───────────────────────────────────────────
async def verify_email(token: str, *, db_path=None) -> None:
    user_id = await asyncio.to_thread(
        session_repo.consume_email_token, token, "verify_email", db_path=db_path
    )
    if user_id is None:
        raise AuthError("INVALID_TOKEN", "링크가 만료되었거나 이미 사용되었습니다.")
    await asyncio.to_thread(user_repo.mark_email_verified, user_id, db_path=db_path)


async def resend_verification(
    user: dict[str, Any], *, db_path=None, mail: MailSettings, auth: AuthSettings, client=None
) -> bool:
    if is_verified(user) or not user.get("email"):
        raise AuthError("ALREADY_VERIFIED", "이미 확인된 계정입니다.")
    return await _send_verification(
        user["user_id"], user["email"], db_path=db_path, mail=mail, auth=auth, client=client
    )


async def forgot_password(
    email: str, *, db_path=None, mail: MailSettings, auth: AuthSettings, client=None
) -> None:
    """계정이 없어도 조용히 끝납니다. 호출부는 언제나 200을 돌려줘야 합니다."""
    user = await asyncio.to_thread(user_repo.get_user_by_email, email, db_path=db_path)
    if user is None or not user.get("password_hash"):
        return
    token = await asyncio.to_thread(
        session_repo.create_email_token, user["user_id"], "reset_password", db_path=db_path
    )
    subject, html = reset_mail(f"{auth.frontend_base_url}/password/reset?token={token}")
    try:
        await send_mail(email, subject, html, mail, client=client)
    except MailError:
        return


async def reset_password(token: str, new_password: str, *, db_path=None) -> None:
    validate_password(new_password)
    user_id = await asyncio.to_thread(
        session_repo.consume_email_token, token, "reset_password", db_path=db_path
    )
    if user_id is None:
        raise AuthError("INVALID_TOKEN", "링크가 만료되었거나 이미 사용되었습니다.")
    digest = await asyncio.to_thread(hash_password, new_password)
    await asyncio.to_thread(user_repo.set_password, user_id, digest, db_path=db_path)
    # 비밀번호가 샜을 수 있으니 다른 기기의 로그인도 전부 끊습니다.
    await asyncio.to_thread(session_repo.delete_user_sessions, user_id, db_path=db_path)


# ── 카카오 ──────────────────────────────────────────────────────────────
async def kakao_callback(
    code: str,
    state: str,
    *,
    db_path=None,
    kakao: KakaoOAuthSettings,
    client=None,
) -> tuple[str, str]:
    """세션 원문 토큰과 돌아갈 경로를 돌려줍니다."""
    next_path = await asyncio.to_thread(session_repo.consume_oauth_state, state, db_path=db_path)
    if next_path is None:
        raise AuthError("INVALID_STATE", "로그인 요청이 만료되었습니다. 다시 시도해 주세요.")
    if not code:
        raise KakaoOAuthError("KAKAO_TOKEN_REJECTED", "인가 코드가 없습니다.")
    access_token = await exchange_token(code, kakao, client=client)
    profile = await fetch_profile(access_token, kakao, client=client)
    user_id = await asyncio.to_thread(_resolve_social_user, profile, db_path)
    await asyncio.to_thread(session_repo.purge_expired, db_path=db_path)
    token, _ = await asyncio.to_thread(session_repo.create_session, user_id, db_path=db_path)
    return token, safe_next(next_path)


def _resolve_social_user(profile: KakaoProfile, db_path) -> str:
    return user_repo.link_or_create_social_user(
        PROVIDER_KAKAO,
        profile.provider_user_id,
        nickname=profile.nickname,
        profile_image_url=profile.profile_image_url,
        db_path=db_path,
    )


# ── 세션 ────────────────────────────────────────────────────────────────
async def session_user(token: str | None, *, db_path=None) -> dict[str, Any] | None:
    if not token:
        return None
    return await asyncio.to_thread(session_repo.resolve_session, token, db_path=db_path)


async def logout(token: str | None, *, db_path=None) -> None:
    if token:
        await asyncio.to_thread(session_repo.delete_session, token, db_path=db_path)


def origin_allowed(origin: str | None, allowed: list[str]) -> bool:
    """CORS 미들웨어는 요청을 막지 않습니다. 쓰기 요청은 여기서 한 번 더 봅니다."""
    if not origin:
        return False
    parts = urlsplit(origin)
    if not parts.scheme or not parts.netloc:
        return False
    return f"{parts.scheme}://{parts.netloc}" in allowed
