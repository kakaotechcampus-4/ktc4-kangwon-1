"""실행 계층이 공유하는 답변 사전검증 충돌과 주소 오류입니다."""

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
