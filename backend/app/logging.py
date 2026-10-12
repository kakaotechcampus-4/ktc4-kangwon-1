"""예외 원문과 연쇄 예외를 제거하고 코드 위치만 운영 로그에 남깁니다."""

from logging import Logger


def log_exception(logger: Logger, message: str, exc: BaseException, *args: object) -> None:
    safe = RuntimeError(type(exc).__name__)
    logger.exception(message, *args, exc_info=(RuntimeError, safe, exc.__traceback__))
