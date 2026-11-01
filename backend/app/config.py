"""환경 파일은 서버·CLI 진입점에서 한 번만 읽습니다."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AddressSettings:
    api_key: str | None = field(default=None, repr=False)
    timeout: float = 15.0

    @classmethod
    def from_env(cls) -> "AddressSettings":
        return cls(api_key=os.environ.get("GEOCODING_API_KEY"))


@dataclass(frozen=True)
class KakaoOAuthSettings:
    """카카오 로그인 설정입니다. 주소 검색 키와 값이 같아도 변수는 분리합니다.

    GEOCODING_API_KEY를 재사용하면 키를 돌릴 때 주소·지도 조회가 같이 죽습니다.
    """

    client_id: str | None = field(default=None, repr=False)
    client_secret: str | None = field(default=None, repr=False)
    redirect_uri: str | None = None
    timeout: float = 10.0

    @classmethod
    def from_env(cls) -> "KakaoOAuthSettings":
        return cls(
            client_id=os.environ.get("KAKAO_REST_API_KEY"),
            client_secret=os.environ.get("KAKAO_CLIENT_SECRET"),
            redirect_uri=os.environ.get("KAKAO_REDIRECT_URI"),
        )


@dataclass(frozen=True)
class MailSettings:
    """Resend로 메일을 보냅니다. REST 호출이라 새 의존성이 없습니다."""

    api_key: str | None = field(default=None, repr=False)
    sender: str | None = None
    timeout: float = 10.0

    @classmethod
    def from_env(cls) -> "MailSettings":
        return cls(api_key=os.environ.get("RESEND_API_KEY"), sender=os.environ.get("MAIL_FROM"))


@dataclass(frozen=True)
class AuthSettings:
    """로그인 뒤 돌아갈 곳과 쿠키 속성입니다.

    쿠키 이름·SameSite·수명은 환경마다 달라질 값이 아니라 상수로 둡니다.
    환경변수는 늘어날수록 운영 서버에 하나 빠뜨려 생기는 사고가 늘어납니다.
    """

    frontend_base_url: str = "http://localhost:3000"
    cookie_secure: bool = True

    @classmethod
    def from_env(cls) -> "AuthSettings":
        raw = os.environ.get("SESSION_COOKIE_SECURE", "true").strip().lower()
        return cls(
            frontend_base_url=(
                os.environ.get("FRONTEND_BASE_URL") or "http://localhost:3000"
            ).rstrip("/"),
            cookie_secure=raw not in {"0", "false", "no"},
        )


def load_environment() -> None:
    load_dotenv(BACKEND_DIR / ".env", override=False)
