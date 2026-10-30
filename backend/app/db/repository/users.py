"""계정과 로그인 수단 저장소입니다."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from app.clock import utc_now_iso
from app.db.connection import connect

from .common import _text


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def get_user(user_id: str, *, db_path=None) -> dict[str, Any] | None:
    with connect(db_path) as db:
        return _row(db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone())


def get_user_by_email(email: str, *, db_path=None) -> dict[str, Any] | None:
    with connect(db_path) as db:
        return _row(
            db.execute("SELECT * FROM users WHERE email=?", (_normalize_email(email),)).fetchone()
        )


def _normalize_email(email: str) -> str:
    # 도메인만 접어도 사람이 대문자로 적은 주소가 중복 계정이 되는 일을 막습니다.
    local, _, domain = _text(email).partition("@")
    return f"{local}@{domain.lower()}" if domain else local


def create_email_user(email: str, password_hash: str, display_name: str | None, *, db_path=None):
    """이메일 가입. 중복이면 sqlite3.IntegrityError가 올라옵니다."""
    user_id = uuid.uuid4().hex
    now = utc_now_iso()
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO users(user_id,email,password_hash,display_name,created_at,last_login_at)"
            " VALUES(?,?,?,?,?,?)",
            (user_id, _normalize_email(email), password_hash, display_name, now, now),
        )
    return user_id


def link_or_create_social_user(
    provider: str,
    provider_user_id: str,
    *,
    nickname: str | None = None,
    profile_image_url: str | None = None,
    db_path=None,
) -> str:
    """소셜 로그인으로 들어온 사람의 계정을 찾고, 없으면 만듭니다.

    users와 user_identities를 한 트랜잭션에서 넣습니다. 둘로 나누면 중간에 죽었을 때
    로그인 수단 없는 계정이 남습니다.
    """
    now = utc_now_iso()
    with connect(db_path) as db:
        found = db.execute(
            "SELECT user_id FROM user_identities WHERE provider=? AND provider_user_id=?",
            (provider, provider_user_id),
        ).fetchone()
        if found is not None:
            user_id = str(found["user_id"])
            db.execute("UPDATE users SET last_login_at=? WHERE user_id=?", (now, user_id))
            return user_id
        user_id = uuid.uuid4().hex
        db.execute(
            "INSERT INTO users(user_id,display_name,profile_image_url,created_at,last_login_at)"
            " VALUES(?,?,?,?,?)",
            (user_id, nickname, profile_image_url, now, now),
        )
        db.execute(
            "INSERT INTO user_identities(provider,provider_user_id,user_id,created_at)"
            " VALUES(?,?,?,?)",
            (provider, provider_user_id, user_id, now),
        )
        return user_id


def attach_identity(provider: str, provider_user_id: str, user_id: str, *, db_path=None) -> None:
    """이미 있는 계정에 소셜 로그인 수단을 더합니다(같은 이메일로 들어온 경우)."""
    with connect(db_path) as db:
        db.execute(
            "INSERT OR IGNORE INTO user_identities(provider,provider_user_id,user_id,created_at)"
            " VALUES(?,?,?,?)",
            (provider, provider_user_id, user_id, utc_now_iso()),
        )


def mark_logged_in(user_id: str, *, db_path=None) -> None:
    with connect(db_path) as db:
        db.execute("UPDATE users SET last_login_at=? WHERE user_id=?", (utc_now_iso(), user_id))


def mark_email_verified(user_id: str, *, db_path=None) -> None:
    with connect(db_path) as db:
        db.execute(
            "UPDATE users SET email_verified_at=? WHERE user_id=? AND email_verified_at IS NULL",
            (utc_now_iso(), user_id),
        )


def set_password(user_id: str, password_hash: str, *, db_path=None) -> None:
    with connect(db_path) as db:
        db.execute("UPDATE users SET password_hash=? WHERE user_id=?", (password_hash, user_id))


def delete_user(user_id: str, *, db_path=None) -> None:
    """탈퇴. 분석 자체는 불변 트리거 때문에 지울 수 없어 소유 연결만 끊습니다(익명화)."""
    with connect(db_path) as db:
        db.execute("DELETE FROM analysis_owners WHERE user_id=?", (user_id,))
        db.execute("DELETE FROM email_tokens WHERE user_id=?", (user_id,))
        db.execute("DELETE FROM user_sessions WHERE user_id=?", (user_id,))
        db.execute("DELETE FROM user_identities WHERE user_id=?", (user_id,))
        db.execute("DELETE FROM users WHERE user_id=?", (user_id,))
