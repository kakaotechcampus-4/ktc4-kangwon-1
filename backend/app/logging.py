"""예외 원문과 연쇄 예외를 제거하고 코드 위치만 운영 로그에 남깁니다."""

import logging
import re
from logging import Logger

from app.storage.scrub import scrub_text


class _HttpQueryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # httpx는 URL 객체를 문자열로 포맷한 뒤 INFO 로그에 남깁니다.
        record.msg = re.sub(
            r"https?://[^\s\"'<>]+", lambda m: scrub_text(m[0]), record.getMessage()
        )
        record.args = ()
        return True


class _AccessQueryFilter(logging.Filter):
    """들어오는 요청 경로에 실린 비밀값을 가립니다.

    protect_http_query_logs 는 httpx 로거만 봐서 나가는 호출만 보호합니다.
    카카오 콜백은 ?code=·?state= 를 달고 **들어오므로** uvicorn.access 가
    그대로 기록합니다. scrub_text 는 "https://"로 시작하는 문자열만 손봐서
    access 로그 형식("GET /path?q HTTP/1.1")에는 걸리지 않습니다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _SENSITIVE_QUERY.sub(r"\1=[REDACTED]", record.getMessage())
        record.args = ()
        return True


# 토큰은 본문으로 받지만, 메일 링크를 눌러 들어온 프론트가 중계하는 경우까지 덮습니다.
_SENSITIVE_QUERY = re.compile(r"\b(code|state|token|access_token)=[^&\s\"']+")

_HTTP_QUERY_FILTER = _HttpQueryFilter()
_ACCESS_QUERY_FILTER = _AccessQueryFilter()


def protect_http_query_logs() -> None:
    logging.getLogger("httpx").addFilter(_HTTP_QUERY_FILTER)
    logging.getLogger("uvicorn.access").addFilter(_ACCESS_QUERY_FILTER)


def log_exception(logger: Logger, message: str, exc: BaseException, *args: object) -> None:
    safe = RuntimeError(type(exc).__name__)
    logger.exception(message, *args, exc_info=(RuntimeError, safe, exc.__traceback__))
