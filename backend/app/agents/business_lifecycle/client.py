import argparse
import json
import os
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

SEOUL_API_BASE_URL = "http://openapi.seoul.go.kr:8088"
SERVICE_NAME = "VwsmTrdarStorQq"

PAGE_SIZE = 1000
TIMEOUT_SECONDS = 10


class SeoulOpenAPIError(RuntimeError):
    """서울 열린데이터광장 API 호출 오류."""


class SeoulOpenAPINoDataError(SeoulOpenAPIError):
    """서울 열린데이터광장에 해당 조건의 자료가 없습니다."""


class FutureQuarterError(ValueError):
    """아직 확정되지 않은 미래 분기를 요청했습니다."""


def get_api_key() -> str:
    api_key = os.getenv(
        "BUSINESS_LIFECYCLE_API_KEY"
    ) or os.getenv(
        "SEOUL_OPEN_API_KEY"
    )

    if not api_key:
        raise SeoulOpenAPIError(
            "BUSINESS_LIFECYCLE_API_KEY "
            "환경변수가 설정되어 있지 않습니다."
        )

    return api_key


def build_url(
    api_key: str,
    start_index: int,
    end_index: int,
    quarter: str,
    area_code: str,
) -> str:
    return (
        f"{SEOUL_API_BASE_URL}"
        f"/{api_key}"
        f"/json"
        f"/{SERVICE_NAME}"
        f"/{start_index}"
        f"/{end_index}"
        f"/{quarter}"
        f"/{area_code}"
    )


def request_page(
    api_key: str,
    quarter: str,
    area_code: str,
    start_index: int,
    end_index: int,
) -> dict[str, Any]:
    url = build_url(
        api_key=api_key,
        start_index=start_index,
        end_index=end_index,
        quarter=quarter,
        area_code=area_code,
    )

    try:
        with urlopen(
            url,
            timeout=TIMEOUT_SECONDS,
        ) as response:
            raw_data = response.read().decode("utf-8")

    except HTTPError as exc:
        raise SeoulOpenAPIError(
            f"서울시 API HTTP 오류: {exc.code}"
        ) from exc

    except URLError as exc:
        raise SeoulOpenAPIError(
            f"서울시 API 연결 실패: {exc.reason}"
        ) from exc

    try:
        return json.loads(raw_data)

    except json.JSONDecodeError as exc:
        raise SeoulOpenAPIError(
            "서울시 API 응답을 JSON으로 해석할 수 없습니다."
        ) from exc


def extract_service_data(
    response_data: dict[str, Any],
) -> dict[str, Any]:
    top_result = response_data.get("RESULT")

    if top_result is not None:
        if top_result.get("CODE") == "INFO-200":
            raise SeoulOpenAPINoDataError(
                f"서울시 API 자료 없음: "
                f"{top_result.get('CODE')} - "
                f"{top_result.get('MESSAGE')}"
            )
        raise SeoulOpenAPIError(
            f"서울시 API 오류: "
            f"{top_result.get('CODE')} - "
            f"{top_result.get('MESSAGE')}"
        )

    service_data = response_data.get(SERVICE_NAME)

    if service_data is None:
        raise SeoulOpenAPIError(
            f"응답에 {SERVICE_NAME} 데이터가 없습니다."
        )

    result = service_data.get("RESULT", {})

    if result.get("CODE") not in (None, "INFO-000"):
        if result.get("CODE") == "INFO-200":
            raise SeoulOpenAPINoDataError(
                f"서울시 API 자료 없음: "
                f"{result.get('CODE')} - "
                f"{result.get('MESSAGE')}"
            )
        raise SeoulOpenAPIError(
            f"서울시 API 오류: "
            f"{result.get('CODE')} - "
            f"{result.get('MESSAGE')}"
        )

    return service_data


def normalize_row(
    row: dict[str, Any],
) -> dict[str, Any]:
    """
    서울시 API 컬럼명을 내부에서 사용하는 이름으로 변환한다.
    """

    return {
        "stdr_yyqu_cd": row.get("STDR_YYQU_CD"),
        "trdar_se_cd": row.get("TRDAR_SE_CD"),
        "trdar_se_cd_nm": row.get("TRDAR_SE_CD_NM"),
        "trdar_cd": row.get("TRDAR_CD"),
        "trdar_cd_nm": row.get("TRDAR_CD_NM"),
        "svc_induty_cd": row.get("SVC_INDUTY_CD"),
        "svc_induty_cd_nm": row.get("SVC_INDUTY_CD_NM"),
        "similr_induty_stor_co": row.get(
            "SIMILR_INDUTY_STOR_CO"
        ),
        "stor_co": row.get("STOR_CO"),
        "frc_stor_co": row.get("FRC_STOR_CO"),
        "opbiz_rt": row.get("OPBIZ_RT"),
        "opbiz_stor_co": row.get("OPBIZ_STOR_CO"),
        "clsbiz_rt": row.get("CLSBIZ_RT"),
        "clsbiz_stor_co": row.get("CLSBIZ_STOR_CO"),
    }


def fetch_store_data(
    area_code: str,
    quarter: str,
) -> list[dict[str, Any]]:
    """
    특정 상권의 특정 분기 데이터를 조회한다.
    """

    api_key = get_api_key()

    rows: list[dict[str, Any]] = []
    start_index = 1

    while True:
        end_index = start_index + PAGE_SIZE - 1

        response_data = request_page(
            api_key=api_key,
            quarter=quarter,
            area_code=area_code,
            start_index=start_index,
            end_index=end_index,
        )

        try:
            service_data = extract_service_data(
                response_data
            )
        except SeoulOpenAPINoDataError:
            return []

        total_count = int(
            service_data.get("list_total_count", 0)
        )

        page_rows = service_data.get("row", [])

        for row in page_rows:
            rows.append(
                normalize_row(row)
            )

        if len(rows) >= total_count:
            break

        if not page_rows:
            break

        start_index += PAGE_SIZE

    return rows


def validate_quarter_code(
    quarter_code: str,
) -> None:
    if len(quarter_code) != 5:
        raise ValueError(
            "분기 코드는 YYYYQ 형식이어야 합니다. 예: 20252"
        )

    quarter = int(quarter_code[4])

    if quarter not in (1, 2, 3, 4):
        raise ValueError(
            "분기는 1~4 중 하나여야 합니다."
        )


def previous_quarter(
    quarter_code: str,
) -> str:
    validate_quarter_code(
        quarter_code
    )

    year = int(quarter_code[:4])
    quarter = int(quarter_code[4])

    quarter -= 1

    if quarter == 0:
        quarter = 4
        year -= 1

    return f"{year}{quarter}"


def latest_closed_quarter(
    today: date | None = None,
) -> str:
    """
    아직 끝나지 않은 현재 분기나 미래 분기를 조회하지 않기 위한 상한입니다.
    실제 사용 가능 여부는 서울시 API 조회 결과로 다시 확인합니다.
    """

    today = today or date.today()
    current_quarter = (today.month - 1) // 3 + 1
    year = today.year
    quarter = current_quarter - 1

    if quarter == 0:
        year -= 1
        quarter = 4

    return f"{year}{quarter}"


def compare_quarters(
    left: str,
    right: str,
) -> int:
    validate_quarter_code(left)
    validate_quarter_code(right)
    left_value = int(left[:4]) * 4 + int(left[4])
    right_value = int(right[:4]) * 4 + int(right[4])
    return (left_value > right_value) - (left_value < right_value)


def get_candidate_quarters(
    *,
    start_quarter: str | None = None,
    count: int = 12,
    today: date | None = None,
) -> list[str]:
    if count <= 0:
        raise ValueError("조회할 후보 분기 수는 1 이상이어야 합니다.")

    quarter = start_quarter or latest_closed_quarter(today)
    validate_quarter_code(quarter)
    latest_allowed = latest_closed_quarter(today)

    if compare_quarters(quarter, latest_allowed) > 0:
        raise FutureQuarterError(
            f"아직 확정되지 않은 분기는 조회하지 않습니다: {quarter}"
        )

    quarters: list[str] = []

    for _ in range(count):
        quarters.append(quarter)
        quarter = previous_quarter(quarter)

    return quarters


def detect_latest_valid_quarter(
    area_code: str,
    *,
    candidate_count: int = 12,
    today: date | None = None,
) -> str:
    """
    서울시 API를 실제로 조회해 해당 상권에서 자료가 있는 최신 분기를 고릅니다.
    """

    for quarter in get_candidate_quarters(
        count=candidate_count,
        today=today,
    ):
        rows = fetch_store_data(
            area_code=area_code,
            quarter=quarter,
        )
        if rows:
            return quarter

    raise SeoulOpenAPINoDataError(
        "최근 후보 분기에서 해당 상권의 점포 개폐업 자료를 찾지 못했습니다."
    )


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

    validate_quarter_code(
        base_quarter
    )

    year = int(base_quarter[:4])
    quarter = int(base_quarter[4])

    if quarter not in (1, 2, 3, 4):
        raise ValueError(
            "분기는 1~4 중 하나여야 합니다."
        )

    if count <= 0:
        raise ValueError(
            "조회할 분기 수는 1 이상이어야 합니다."
        )

    quarters: list[str] = []

    current_year = year
    current_quarter = quarter

    for _ in range(count):
        quarters.append(
            f"{current_year}{current_quarter}"
        )

        current_quarter -= 1

        if current_quarter == 0:
            current_quarter = 4
            current_year -= 1

    quarters.reverse()

    return quarters


def fetch_store_data_for_quarters(
    area_code: str,
    quarters: list[str],
) -> list[dict[str, Any]]:
    """
    여러 분기의 데이터를 조회하여 하나의 리스트로 합친다.
    """

    all_rows: list[dict[str, Any]] = []

    for quarter in quarters:
        rows = fetch_store_data(
            area_code=area_code,
            quarter=quarter,
        )

        all_rows.extend(rows)

    return all_rows


def fetch_recent_store_data(
    area_code: str,
    base_quarter: str,
    quarter_count: int = 12,
) -> list[dict[str, Any]]:
    """
    기준 분기를 기준으로 최근 N개 분기의 데이터를 조회한다.

    실제 preprocess.py에서는 이 함수를 호출하면 된다.
    """

    quarters = get_recent_quarters(
        base_quarter=base_quarter,
        count=quarter_count,
    )

    return fetch_store_data_for_quarters(
        area_code=area_code,
        quarters=quarters,
    )


def main() -> None:
    """
    로컬 테스트용 CLI.

    실제 서비스 로직에서는 사용하지 않고
    fetch_recent_store_data()를 직접 호출한다.
    """

    parser = argparse.ArgumentParser(
        description="서울시 상권 개폐업 데이터 조회"
    )

    parser.add_argument(
        "--area-code",
        required=True,
        help="서울시 상권코드",
    )

    parser.add_argument(
        "--base-quarter",
        required=True,
        help="기준 분기. 예: 20252",
    )

    parser.add_argument(
        "--count",
        type=int,
        default=12,
        help="조회할 최근 분기 수. 기본값 12",
    )

    args = parser.parse_args()

    quarters = get_recent_quarters(
        base_quarter=args.base_quarter,
        count=args.count,
    )

    print("조회 상권:", args.area_code)
    print("기준 분기:", args.base_quarter)
    print("조회 분기 수:", len(quarters))
    print("조회 분기:", ", ".join(quarters))

    rows = fetch_recent_store_data(
        area_code=args.area_code,
        base_quarter=args.base_quarter,
        quarter_count=args.count,
    )

    print("전체 조회 행 수:", len(rows))

    if rows:
        print()
        print("첫 번째 데이터:")
        print(
            json.dumps(
                rows[0],
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
