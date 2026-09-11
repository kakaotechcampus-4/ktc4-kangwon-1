"""서울 열린데이터광장 Open API 클라이언트 (길단위인구 · 상권영역).

요청 형식: {base}/{KEY}/json/{SERVICE}/{START}/{END}/[{추가 경로 인자}/]
응답 형식: {"<SERVICE>": {"list_total_count": N, "RESULT": {"CODE": "INFO-000", ...}, "row": [...]}}

2026-09-07 실호출로 확인한 것:
- 상권영역 약 1,650곳(2페이지). 길단위인구는 2021Q1 부터 22개 분기가 한 서비스에 섞여 있고
  (3.6만 행, 37페이지) 분기순 정렬도 아니다.
- 경로 끝에 기준년분기(예: 20262) 를 붙이면 그 분기만 온다(1,648행). **상권코드 필터는 안 먹는다.**
  그래서 오늘 날짜 기준 분기부터 거꾸로 탐침해 데이터가 있는 최신 분기를 찾는다.
- 오늘 분기는 아직 미발행일 수 있어 탐침이 필요하다.

키가 없으면 샘플로 대체하지 않고 에러를 낸다 — 샘플 수치를 실데이터로 착각하는 사고를 막는다.
"""

from __future__ import annotations

from datetime import date

import httpx

from .config import Settings, load_dotenv_if_present
from .models import FlpopRecord, TrdarArea


class SeoulOpenApiError(RuntimeError):
    pass


class MissingApiKeyError(RuntimeError):
    """FLOATING_POPULATION_API_KEY 가 없음 — data.seoul.go.kr 에서 무료·즉시 발급."""


def quarter_code(d: date) -> str:
    """2026-09-09 → '20263' (기준년분기 코드)."""
    return f"{d.year}{(d.month - 1) // 3 + 1}"


def previous_quarter(code: str) -> str:
    year, q = int(code[:4]), int(code[4])
    return f"{year - 1}4" if q == 1 else f"{year}{q - 1}"


class SeoulOpenDataClient:
    def __init__(
        self,
        settings: Settings | None = None,
        http: httpx.Client | None = None,
        today: date | None = None,
    ):
        if settings is None:
            load_dotenv_if_present()
            settings = Settings.from_env()
        self.settings = settings
        # TODO 오케스트레이터가 세 에이전트를 동시에 돌리게 되면 httpx.AsyncClient 로 바꾼다.
        #      (1차 코드리뷰 지적사항. 지금은 팀의 다른 에이전트가 모두 동기라 맞춰 둔다)
        self.http = http or httpx.Client(timeout=settings.request_timeout_s)
        self.today = today or date.today()
        if not self.settings.api_key:
            raise MissingApiKeyError(
                "FLOATING_POPULATION_API_KEY 가 설정되지 않았습니다. "
                "https://data.seoul.go.kr 에서 발급(무료·즉시) 후 .env 에 넣어주세요."
            )

    # ---- public -------------------------------------------------------

    def fetch_trdar_areas(self) -> list[TrdarArea]:
        """서울시 전체 상권영역(중심좌표·구·행정동 포함). 약 1,650곳, 2페이지."""
        rows = self._fetch_all(
            self.settings.trdar_area_service, self.settings.trdar_area_max_pages
        )
        return [TrdarArea.from_api_row(r) for r in rows]

    def fetch_flpop(self, trdar_cds: set[str]) -> tuple[str, list[FlpopRecord]]:
        """최신 분기의 길단위인구를 받아 대상 상권만 거른다.

        반환: (기준년분기, 레코드 목록). API 가 상권코드 필터를 지원하지 않아 그 분기 전체를
        받은 뒤 거른다 — 1회 호출(4페이지)로 끝나므로 그대로 둔다.
        """
        quarter = self.latest_quarter()
        rows = self._fetch_all(
            self.settings.flpop_service, self.settings.flpop_max_pages, extra=quarter
        )
        records = [FlpopRecord.from_api_row(r) for r in rows]
        return quarter, [r for r in records if r.trdar_cd in trdar_cds]

    def latest_quarter(self) -> str:
        """데이터가 존재하는 가장 최신 분기. 오늘 분기부터 거꾸로 1행씩 탐침한다."""
        code = quarter_code(self.today)
        for _ in range(self.settings.quarter_probe_limit):
            body = self._get(self.settings.flpop_service, 1, 1, extra=code)
            svc = body.get(self.settings.flpop_service) or {}
            if svc.get("RESULT", {}).get("CODE") == "INFO-000" and int(
                svc.get("list_total_count", 0)
            ):
                return code
            code = previous_quarter(code)
        raise SeoulOpenApiError(
            f"최근 {self.settings.quarter_probe_limit}개 분기에 데이터가 없습니다"
        )

    # ---- internals ----------------------------------------------------

    def _fetch_all(self, service: str, max_pages: int, extra: str | None = None) -> list[dict]:
        rows: list[dict] = []
        start = 1
        for _ in range(max_pages):
            end = start + self.settings.page_size - 1
            payload = self._get(service, start, end, extra=extra)
            body = payload.get(service)
            if body is None:
                raise SeoulOpenApiError(
                    f"응답에 '{service}' 키가 없음 — 서비스명 오류 가능. 응답: {str(payload)[:200]}"
                )
            code = body.get("RESULT", {}).get("CODE", "")
            if code == "INFO-200":  # 해당하는 데이터 없음 (마지막 페이지 이후)
                break
            if code and code != "INFO-000":
                message = body.get("RESULT", {}).get("MESSAGE")
                raise SeoulOpenApiError(f"{service} {code}: {message}")
            page = body.get("row", [])
            rows.extend(page)
            total = int(body.get("list_total_count", 0))
            if end >= total or not page:
                break
            start = end + 1
        return rows

    def _get(self, service: str, start: int, end: int, extra: str | None = None) -> dict:
        s = self.settings
        url = f"{s.base_url}/{s.api_key}/json/{service}/{start}/{end}/"
        if extra:
            url += f"{extra}/"
        resp = self.http.get(url)
        resp.raise_for_status()
        return resp.json()
