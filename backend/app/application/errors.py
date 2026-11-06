"""실행 계층이 공유하는 답변 사전검증 충돌과 주소 오류입니다."""

import sqlite3

INTERRUPTED_MESSAGE = "서비스 점검으로 분석이 멈췄어요. 다시 분석해 주세요."
ADDRESS_INPUT_ERRORS = frozenset(
    {"EMPTY_ADDRESS", "NOT_FOUND", "ADDRESS_AMBIGUOUS", "ADDRESS_MISMATCH", "ADDRESS_TOO_LONG"}
)


class AnalysisConflictError(ValueError):
    pass


class AddressError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class RawStorageError(sqlite3.DatabaseError):
    """원문 저장 실패는 에이전트 실패로 변환하지 않고 서비스까지 전파합니다."""
