"""모델 자유 문장의 숫자 표기를 공통으로 확인합니다."""


def has_digit(text: str) -> bool:
    return any(char.isnumeric() for char in text)
