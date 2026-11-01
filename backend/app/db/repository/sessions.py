"""세션·OAuth state·메일 토큰·로그인 시도 저장소입니다.

쿠키와 메일로 나가는 원문 토큰은 어디에도 저장하지 않고 sha256 해시만 둡니다.
DB가 통째로 새도 토큰을 되살릴 수 없습니다.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from app.clock import utc_now_iso
from app.db.connection import connect

SESSION_TTL = timedelta(days=14)
OAUTH_STATE_TTL = timedelta(minutes=5)
VERIFY_TOKEN_TTL = timedelta(hours=24)
RESET_TOKEN_TTL = timedelta(minutes=30)
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_MAX_FAILURES = 5
# 폴링이 1~3초마다 들어옵니다. 매번 쓰면 분석 중 쓰기와 잠금을 다툽니다.
LAST_SEEN_THROTTLE = timedelta(minutes=5)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


# ── 세션 ────────────────────────────────────────────────────────────────
def create_session(user_id: str, *, db_path=None) -> tuple[str, datetime]:
    """원문 토큰과 만료 시각을 돌려줍니다. 원문은 이 반환값이 유일한 출처입니다."""
    token = new_token()
    now = _now()
    expires = now + SESSION_TTL
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO user_sessions(session_id,user_id,created_at,expires_at,last_seen_at)"
            " VALUES(?,?,?,?,?)",
            (hash_token(token), user_id, _iso(now), _iso(expires), _iso(now)),
        )
    return token, expires


def resolve_session(token: str, *, db_path=None) -> dict[str, Any] | None:
    """세션에 걸린 사용자를 돌려줍니다. 만료됐으면 None입니다."""
    if not token:
        return None
    now = _now()
    with connect(db_path) as db:
        row = db.execute(
            "SELECT s.session_id, s.last_seen_at, u.* FROM user_sessions s"
            " JOIN users u ON u.user_id = s.user_id"
            " WHERE s.session_id=? AND s.expires_at > ?",
            (hash_token(token), _iso(now)),
        ).fetchone()
        if row is None:
            return None
        _touch(db, row, now)
        user = dict(row)
        user.pop("session_id", None)
        user.pop("last_seen_at", None)
        return user


def _touch(db: sqlite3.Connection, row: sqlite3.Row, now: datetime) -> None:
    """마지막 접속 시각은 가끔만 씁니다(§폴링 경합)."""
    try:
        seen = datetime.fromisoformat(str(row["last_seen_at"]))
    except ValueError:
        seen = now - LAST_SEEN_THROTTLE
    if now - seen < LAST_SEEN_THROTTLE:
        return
    db.execute(
        "UPDATE user_sessions SET last_seen_at=?, expires_at=? WHERE session_id=?",
        (_iso(now), _iso(now + SESSION_TTL), row["session_id"]),
    )


def delete_session(token: str, *, db_path=None) -> None:
    with connect(db_path) as db:
        db.execute("DELETE FROM user_sessions WHERE session_id=?", (hash_token(token),))


def delete_user_sessions(user_id: str, *, db_path=None) -> None:
    """비밀번호를 바꾸면 다른 기기의 로그인도 전부 끊습니다."""
    with connect(db_path) as db:
        db.execute("DELETE FROM user_sessions WHERE user_id=?", (user_id,))


# ── OAuth state ─────────────────────────────────────────────────────────
def create_oauth_state(next_path: str, *, db_path=None) -> str:
    state = new_token()
    now = _now()
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO oauth_states(state,next_path,created_at,expires_at) VALUES(?,?,?,?)",
            (state, next_path, _iso(now), _iso(now + OAUTH_STATE_TTL)),
        )
    return state


def consume_oauth_state(state: str, *, db_path=None) -> str | None:
    """한 번만 쓰입니다. 지우면서 돌려주므로 재사용·위조 요청이 같이 막힙니다."""
    if not state:
        return None
    with connect(db_path) as db:
        row = db.execute(
            "DELETE FROM oauth_states WHERE state=? AND expires_at > ? RETURNING next_path",
            (state, _iso(_now())),
        ).fetchone()
        return str(row["next_path"]) if row is not None else None


# ── 메일 토큰 ───────────────────────────────────────────────────────────
def create_email_token(user_id: str, purpose: str, *, db_path=None) -> str:
    ttl = VERIFY_TOKEN_TTL if purpose == "verify_email" else RESET_TOKEN_TTL
    token = new_token()
    now = _now()
    with connect(db_path) as db:
        # 같은 용도의 옛 링크는 무효로 만듭니다. 메일을 여러 번 받아도 마지막 것만 삽니다.
        db.execute("DELETE FROM email_tokens WHERE user_id=? AND purpose=?", (user_id, purpose))
        db.execute(
            "INSERT INTO email_tokens(token_hash,user_id,purpose,created_at,expires_at)"
            " VALUES(?,?,?,?,?)",
            (hash_token(token), user_id, purpose, _iso(now), _iso(now + ttl)),
        )
    return token


def consume_email_token(token: str, purpose: str, *, db_path=None) -> str | None:
    if not token:
        return None
    with connect(db_path) as db:
        row = db.execute(
            "DELETE FROM email_tokens WHERE token_hash=? AND purpose=? AND expires_at > ?"
            " RETURNING user_id",
            (hash_token(token), purpose, _iso(_now())),
        ).fetchone()
        return str(row["user_id"]) if row is not None else None


# ── 로그인 시도 ─────────────────────────────────────────────────────────
def record_login_attempt(email: str, *, succeeded: bool, db_path=None) -> None:
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO login_attempts(email,attempted_at,succeeded) VALUES(?,?,?)",
            (email, utc_now_iso(), 1 if succeeded else 0),
        )


def too_many_failures(email: str, *, db_path=None) -> bool:
    since = _iso(_now() - LOGIN_WINDOW)
    with connect(db_path) as db:
        count = db.execute(
            "SELECT count(*) FROM login_attempts"
            " WHERE email=? AND succeeded=0 AND attempted_at > ?",
            (email, since),
        ).fetchone()[0]
    return int(count) >= LOGIN_MAX_FAILURES


# ── 청소 ────────────────────────────────────────────────────────────────
def purge_expired(*, db_path=None) -> None:
    """별도 스케줄러가 없어 로그인 성공 때 기회적으로 치웁니다."""
    now = _iso(_now())
    stale = _iso(_now() - LOGIN_WINDOW)
    with connect(db_path) as db:
        db.execute("DELETE FROM user_sessions WHERE expires_at <= ?", (now,))
        db.execute("DELETE FROM oauth_states WHERE expires_at <= ?", (now,))
        db.execute("DELETE FROM email_tokens WHERE expires_at <= ?", (now,))
        db.execute("DELETE FROM login_attempts WHERE attempted_at <= ?", (stale,))
