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

import asyncio
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
    """서울 열린데이터광장 비동기 클라이언트.

    오케스트레이터가 분석 에이전트를 `asyncio.gather` 로 동시에 돌리므로 동기 호출을 쓰면
    이벤트 루프가 통째로 멈춘다(`AGENTS.md` 2번 규칙). 클라이언트를 주입하지 않으면 여기서
    만들고, 그 경우 `aclose()` 로 닫을 책임도 여기에 있다.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        http: httpx.AsyncClient | None = None,
        today: date | None = None,
    ):
        if settings is None:
            load_dotenv_if_present()
            settings = Settings.from_env()
        self.settings = settings
        self._http = http
        self._owns_http = http is None
        self.today = today or date.today()
        if not self.settings.api_key:
            raise MissingApiKeyError(
                "FLOATING_POPULATION_API_KEY 가 설정되지 않았습니다. "
                "https://data.seoul.go.kr 에서 발급(무료·즉시) 후 .env 에 넣어주세요."
            )

    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self.settings.request_timeout_s)
            self._owns_http = True
        return self._http

    async def aclose(self) -> None:
        if self._http is not None and self._owns_http:
            await self._http.aclose()
        self._http = None

    async def __aenter__(self) -> SeoulOpenDataClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # ---- public -------------------------------------------------------

    async def fetch_trdar_areas(self) -> list[TrdarArea]:
        """서울시 전체 상권영역(중심좌표·구·행정동 포함). 약 1,650곳, 2페이지."""
        rows = await self._fetch_all(
            self.settings.trdar_area_service, self.settings.trdar_area_max_pages
        )
        return [TrdarArea.from_api_row(r) for r in rows]

    async def fetch_flpop(self, trdar_cds: set[str]) -> tuple[str, list[FlpopRecord]]:
        """최신 분기의 길단위인구를 받아 대상 상권만 거른다.

        반환: (기준년분기, 레코드 목록). API 가 상권코드 필터를 지원하지 않아 그 분기 전체를
        받은 뒤 거른다 — 1회 호출(4페이지)로 끝나므로 그대로 둔다.
        """
        quarter = await self.latest_quarter()
        rows = await self._fetch_all(
            self.settings.flpop_service, self.settings.flpop_max_pages, extra=quarter
        )
        records = [FlpopRecord.from_api_row(r) for r in rows]
        return quarter, [r for r in records if r.trdar_cd in trdar_cds]

    async def fetch_flpop_series(
        self, trdar_cds: set[str], quarters: int
    ) -> list[tuple[str, list[FlpopRecord]]]:
        """최신 분기부터 거꾸로 `quarters` 개 분기를 받아 **오래된 순**으로 돌려준다.

        반환: [(기준년분기, 레코드 목록), ...]. 자료가 없는 분기는 빈 목록으로 남긴다 —
        빼버리면 리포트가 그래프에 구멍이 있다는 걸 알 수 없다.

        분기끼리는 서로 의존하지 않으므로 **한꺼번에 받는다**(`asyncio.gather`). 순차로 받으면
        분기 수에 비례해 느려지는데(12개 분기 3.7초), 동시에 받으면 가장 느린 한 분기 시간에
        수렴한다. 최신 분기를 찾는 탐침만 순차다 — 앞 분기 결과를 봐야 다음을 정하기 때문이다.
        """
        code = await self.latest_quarter()
        codes = []
        for _ in range(max(1, quarters)):
            codes.append(code)
            code = previous_quarter(code)
        codes.reverse()  # 오래된 순

        pages = await asyncio.gather(
            *(
                self._fetch_all(self.settings.flpop_service, self.settings.flpop_max_pages, extra=c)
                for c in codes
            )
        )
        series: list[tuple[str, list[FlpopRecord]]] = []
        for c, rows in zip(codes, pages, strict=True):
            records = [FlpopRecord.from_api_row(r) for r in rows]
            series.append((c, [r for r in records if r.trdar_cd in trdar_cds]))
        return series

    async def latest_quarter(self) -> str:
        """데이터가 존재하는 가장 최신 분기. 오늘 분기부터 거꾸로 1행씩 탐침한다."""
        code = quarter_code(self.today)
        for _ in range(self.settings.quarter_probe_limit):
            body = await self._get(self.settings.flpop_service, 1, 1, extra=code)
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

    async def _fetch_all(
        self, service: str, max_pages: int, extra: str | None = None
    ) -> list[dict]:
        rows: list[dict] = []
        start = 1
        for _ in range(max_pages):
            end = start + self.settings.page_size - 1
            payload = await self._get(service, start, end, extra=extra)
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

    async def _get(self, service: str, start: int, end: int, extra: str | None = None) -> dict:
        s = self.settings
        url = f"{s.base_url}/{s.api_key}/json/{service}/{start}/{end}/"
        if extra:
            url += f"{extra}/"
        resp = await self.http().get(url)
        resp.raise_for_status()
        return resp.json()
