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


_HTTP_QUERY_FILTER = _HttpQueryFilter()


def protect_http_query_logs() -> None:
    logging.getLogger("httpx").addFilter(_HTTP_QUERY_FILTER)


def log_exception(logger: Logger, message: str, exc: BaseException, *args: object) -> None:
    safe = RuntimeError(type(exc).__name__)
    logger.exception(message, *args, exc_info=(RuntimeError, safe, exc.__traceback__))
