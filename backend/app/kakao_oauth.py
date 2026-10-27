"""카카오 로그인의 외부 호출만 담당합니다. 판단·저장은 services/auth.py가 합니다."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import KakaoOAuthSettings

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
PROFILE_URL = "https://kapi.kakao.com/v2/user/me"


class KakaoOAuthError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class KakaoProfile:
    """카카오가 돌려준 신원입니다. 닉네임·사진은 선택 동의라 없을 수 있습니다."""

    __slots__ = ("provider_user_id", "nickname", "profile_image_url")

    def __init__(self, provider_user_id: str, nickname: str | None, profile_image_url: str | None):
        self.provider_user_id = provider_user_id
        self.nickname = nickname
        self.profile_image_url = profile_image_url


def _require(settings: KakaoOAuthSettings) -> tuple[str, str]:
    if not (settings.client_id or "").strip() or not (settings.redirect_uri or "").strip():
        raise KakaoOAuthError(
            "KAKAO_CONFIG_ERROR", "KAKAO_REST_API_KEY와 KAKAO_REDIRECT_URI를 확인하세요."
        )
    return settings.client_id.strip(), settings.redirect_uri.strip()  # type: ignore[union-attr]


def authorize_url(settings: KakaoOAuthSettings, *, state: str) -> str:
    client_id, redirect_uri = _require(settings)
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


async def exchange_token(
    code: str, settings: KakaoOAuthSettings, *, client: httpx.AsyncClient | None = None
) -> str:
    """인가코드를 액세스 토큰으로 바꿉니다. 토큰은 저장하지 않고 프로필 조회에만 씁니다."""
    client_id, redirect_uri = _require(settings)
    if client is None:
        async with httpx.AsyncClient(timeout=settings.timeout) as owned:
            return await exchange_token(code, settings, client=owned)
    form = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if (settings.client_secret or "").strip():
        form["client_secret"] = settings.client_secret.strip()  # type: ignore[union-attr]
    try:
        response = await client.post(TOKEN_URL, data=form, timeout=settings.timeout)
    except httpx.HTTPError as exc:
        raise KakaoOAuthError("KAKAO_UNAVAILABLE", "카카오에 연결하지 못했습니다.") from exc
    if response.status_code >= 500:
        raise KakaoOAuthError("KAKAO_UNAVAILABLE", "카카오 응답이 올바르지 않습니다.")
    body = _json(response)
    if response.status_code >= 400:
        # 인가코드 재사용·만료가 여기서 잡힙니다. 원문 code 값은 남기지 않습니다.
        raise KakaoOAuthError("KAKAO_TOKEN_REJECTED", str(body.get("error") or "토큰 교환 실패"))
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        raise KakaoOAuthError("KAKAO_TOKEN_REJECTED", "액세스 토큰이 없습니다.")
    return token


async def fetch_profile(
    access_token: str, settings: KakaoOAuthSettings, *, client: httpx.AsyncClient | None = None
) -> KakaoProfile:
    if client is None:
        async with httpx.AsyncClient(timeout=settings.timeout) as owned:
            return await fetch_profile(access_token, settings, client=owned)
    try:
        response = await client.get(
            PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=settings.timeout,
        )
    except httpx.HTTPError as exc:
        raise KakaoOAuthError("KAKAO_UNAVAILABLE", "카카오에 연결하지 못했습니다.") from exc
    if response.status_code >= 500:
        raise KakaoOAuthError("KAKAO_UNAVAILABLE", "카카오 응답이 올바르지 않습니다.")
    if response.status_code >= 400:
        raise KakaoOAuthError("KAKAO_PROFILE_REJECTED", "사용자 정보를 받지 못했습니다.")
    return _profile(_json(response))


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise KakaoOAuthError("KAKAO_UNAVAILABLE", "카카오 응답을 해석하지 못했습니다.") from exc
    return body if isinstance(body, dict) else {}


def _profile(body: dict[str, Any]) -> KakaoProfile:
    # 카카오 id는 int64입니다. 문자열로 보관해 자릿수 손실을 피합니다.
    raw_id = body.get("id")
    if not isinstance(raw_id, int | str) or not str(raw_id).strip():
        raise KakaoOAuthError("KAKAO_PROFILE_REJECTED", "사용자 식별자가 없습니다.")
    raw_account = body.get("kakao_account")
    account: dict[str, Any] = raw_account if isinstance(raw_account, dict) else {}
    raw_profile = account.get("profile")
    profile: dict[str, Any] = raw_profile if isinstance(raw_profile, dict) else {}
    return KakaoProfile(
        provider_user_id=str(raw_id).strip(),
        nickname=_text(profile.get("nickname")),
        profile_image_url=_text(profile.get("profile_image_url")),
    )


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
