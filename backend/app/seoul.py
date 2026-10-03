"""서울 열린데이터 API의 비동기 전송·본문 검증을 공유합니다."""

import httpx


class SeoulOpenApiError(RuntimeError):
    """키나 원문 응답을 노출하지 않는 서울 API 오류입니다."""


class SeoulOpenApiTimeout(SeoulOpenApiError):
    """연결 오류와 구분하는 안전한 시간 초과입니다."""


def previous_quarter(code: str) -> str:
    if len(code) != 5 or not code.isdigit() or code[-1] not in "1234":
        raise ValueError("분기는 YYYYQ 형식이어야 합니다.")
    year, quarter = int(code[:4]), int(code[-1])
    return f"{year - 1}4" if quarter == 1 else f"{year}{quarter - 1}"


async def request_json(
    http: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    service: str,
    start: int,
    end: int,
    extra: str | None = None,
) -> dict:
    url = f"{base_url.rstrip('/')}/{api_key}/json/{service}/{start}/{end}/"
    if extra:
        url += extra.strip("/") + "/"
    try:
        response = await http.get(url)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("객체가 아닌 응답")
        top = payload.get("RESULT", {})
        if not isinstance(top, dict):
            raise ValueError("잘못된 결과 코드")
        if top.get("CODE") not in (None, "INFO-000", "INFO-200"):
            raise SeoulOpenApiError("서울 API가 요청을 거절했습니다.")
        body = payload.get(service)
        if body is not None:
            if not isinstance(body, dict) or not isinstance(body.get("RESULT", {}), dict):
                raise ValueError("잘못된 서비스 본문")
            if body.get("RESULT", {}).get("CODE") not in (None, "INFO-000", "INFO-200"):
                raise SeoulOpenApiError("서울 API가 요청을 거절했습니다.")
            rows = body.get("row", [])
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("잘못된 행 목록")
            if int(body.get("list_total_count", 0)) < 0:
                raise ValueError("잘못된 행 수")
        return payload
    except httpx.TimeoutException as exc:
        raise SeoulOpenApiTimeout("서울 API 응답 시간이 초과되었습니다.") from exc
    except httpx.HTTPError as exc:
        raise SeoulOpenApiError("서울 API 연결 또는 HTTP 응답에 실패했습니다.") from exc
    except (ValueError, TypeError, OverflowError) as exc:
        raise SeoulOpenApiError("서울 API 응답 형식이 올바르지 않습니다.") from exc
