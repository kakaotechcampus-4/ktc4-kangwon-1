"""모델 자유 문장의 숫자 표기를 공통으로 확인합니다."""

import re

IDENTIFIERS = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Z][0-9]{3}[A-Z]?|f_[0-9a-f]{8})(?![A-Za-z0-9_])"
    r"|(?<!\w)20[0-9]{2}[1-4](?!\w)"
)


def has_digit(text: str) -> bool:
    return any(char.isnumeric() for char in IDENTIFIERS.sub("", text))
