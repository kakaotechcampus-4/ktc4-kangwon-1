"""비밀번호 해싱입니다. 표준 라이브러리 scrypt만 쓰고 외부 의존성을 늘리지 않습니다."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

# 파라미터를 해시 문자열에 함께 담아, 나중에 비용을 올려도 옛 해시를 검증할 수 있게 합니다.
_PREFIX = "scrypt"
_N = 2**14
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128


class PasswordPolicyError(ValueError):
    """비밀번호가 정책에 맞지 않습니다."""


def validate_password(password: str) -> str:
    """길이만 봅니다. 문자 종류를 강제하면 오히려 외우기 쉬운 약한 비밀번호를 부릅니다."""
    if not isinstance(password, str):
        raise PasswordPolicyError("비밀번호를 입력해 주세요.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"비밀번호는 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"비밀번호는 {MAX_PASSWORD_LENGTH}자 이하여야 합니다.")
    return password


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _derive(password: str, salt: bytes, *, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=dklen)


def hash_password(password: str) -> str:
    """CPU를 쓰는 동기 함수입니다. 호출부에서 asyncio.to_thread로 감싸세요."""
    validate_password(password)
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = _derive(password, salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"{_PREFIX}${_N}${_R}${_P}${_b64(salt)}${_b64(derived)}"


def verify_password(password: str, stored: str | None) -> bool:
    """형식이 깨졌거나 해시가 없으면 조용히 False입니다. 어느 쪽이 틀렸는지 알리지 않습니다."""
    if not stored or not isinstance(password, str):
        return False
    try:
        prefix, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if prefix != _PREFIX:
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(hash_b64, validate=True)
        derived = _derive(password, salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(derived, expected)
