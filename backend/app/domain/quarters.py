def previous_quarter(code: str) -> str:
    return shift_quarter(code, -1)


def shift_quarter(code: str, count: int) -> str:
    """YYYYQ 분기를 이동합니다. 양수는 이후, 음수는 이전 분기입니다."""
    if len(code) != 5 or not code.isdigit() or code[-1] not in "1234":
        raise ValueError("분기는 YYYYQ 형식이어야 합니다.")
    year, quarter = int(code[:4]), int(code[-1])
    index = year * 4 + quarter - 1 + count
    return f"{index // 4}{index % 4 + 1}"


def validate_quarter_code(
    quarter_code: str,
) -> None:
    if len(quarter_code) != 5:
        raise ValueError("분기 코드는 YYYYQ 형식이어야 합니다. 예: 20252")

    quarter = int(quarter_code[4])

    if quarter not in (1, 2, 3, 4):
        raise ValueError("분기는 1~4 중 하나여야 합니다.")


def get_recent_quarters(
    base_quarter: str,
    count: int = 12,
) -> list[str]:
    """
    기준 분기를 포함한 최근 N개 분기 코드를 생성한다.

    예:
    base_quarter="20252", count=12
    → 20223 ~ 20252
    """

    validate_quarter_code(base_quarter)

    quarter = int(base_quarter[4])

    if quarter not in (1, 2, 3, 4):
        raise ValueError("분기는 1~4 중 하나여야 합니다.")

    if count <= 0:
        raise ValueError("조회할 분기 수는 1 이상이어야 합니다.")

    return [shift_quarter(base_quarter, -offset) for offset in range(count - 1, -1, -1)]
