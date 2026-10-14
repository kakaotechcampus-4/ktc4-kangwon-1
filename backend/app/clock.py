"""저장 시각은 시간대가 명시된 UTC ISO 문자열로 만듭니다."""

from datetime import UTC, datetime


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
