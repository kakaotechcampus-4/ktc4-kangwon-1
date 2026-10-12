"""서울 열린데이터광장 Open API 클라이언트 (길단위인구 · 상권영역 · 주거인구 · 직장인구).

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

from app.seoul import SeoulOpenApiError, previous_quarter, request_json

from .config import Settings
from .models import FlpopRecord, TrdarArea


class MissingApiKeyError(RuntimeError):
    """FLOATING_POPULATION_API_KEY 가 없음 — data.seoul.go.kr 에서 무료·즉시 발급."""


def quarter_code(d: date) -> str:
    """2026-09-09 → '20263' (기준년분기 코드)."""
    return f"{d.year}{(d.month - 1) // 3 + 1}"


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
            settings = Settings.from_env()
        self.settings = settings
        self._http = http
        self._owns_http = http is None
        self.today = today or date.today()
        self._latest_quarter: str | None = None
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
        try:
            return [TrdarArea.from_api_row(r) for r in rows]
        except (ValueError, TypeError, KeyError) as exc:
            raise SeoulOpenApiError("상권영역 응답의 필드가 올바르지 않습니다.") from exc

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

        tasks = [
            asyncio.create_task(
                self._fetch_all(self.settings.flpop_service, self.settings.flpop_max_pages, extra=c)
            )
            for c in codes
        ]
        try:
            pages = await asyncio.gather(*tasks)
        except BaseException:
            # 한 조회가 실패하거나 부모가 취소되어도 다른 조회를 닫힌 클라이언트에
            # 남겨 두지 않습니다. 정리 중 재취소도 자식의 finally를 끊지 않습니다.
            for task in tasks:
                if not task.done():
                    task.cancel()
            settled = asyncio.gather(*tasks, return_exceptions=True)
            while not settled.done():
                try:
                    await asyncio.shield(settled)
                except asyncio.CancelledError:
                    continue
            settled.result()
            raise
        series: list[tuple[str, list[FlpopRecord]]] = []
        for c, rows in zip(codes, pages, strict=True):
            try:
                records = [FlpopRecord.from_api_row(r) for r in rows]
            except (ValueError, TypeError, KeyError) as exc:
                raise SeoulOpenApiError("유동인구 응답의 필드가 올바르지 않습니다.") from exc
            series.append((c, [r for r in records if r.trdar_cd in trdar_cds]))
        return series

    async def latest_quarter(self) -> str:
        """데이터가 존재하는 가장 최신 분기. 오늘 분기부터 거꾸로 1행씩 탐침한다."""
        if self._latest_quarter is not None:
            return self._latest_quarter
        code = quarter_code(self.today)
        for _ in range(self.settings.quarter_probe_limit):
            body = await self._get(self.settings.flpop_service, 1, 1, extra=code)
            svc = body.get(self.settings.flpop_service) or {}
            if svc.get("RESULT", {}).get("CODE") == "INFO-000" and int(
                svc.get("list_total_count", 0)
            ):
                self._latest_quarter = code
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
            body = await self._get_page(service, start, end, extra=extra)
            if body.get("RESULT", {}).get("CODE") == "INFO-200":  # 마지막 페이지 이후
                break
            page = body.get("row", [])
            rows.extend(page)
            total = int(body.get("list_total_count", 0))
            if end >= total or not page:
                break
            start = end + 1
        return rows

    async def _get_page(self, service: str, start: int, end: int, extra: str | None = None) -> dict:
        """한 페이지의 서비스 본문. 결과 코드가 정상(INFO-000)·자료 없음(INFO-200)이 아니면 예외."""
        payload = await self._get(service, start, end, extra=extra)
        body = payload.get(service)
        if body is None:
            if payload.get("RESULT", {}).get("CODE") == "INFO-200":
                return {"RESULT": {"CODE": "INFO-200"}, "row": [], "list_total_count": 0}
            raise SeoulOpenApiError(f"응답에 '{service}' 키가 없습니다. 서비스명을 확인해 주세요.")
        code = body.get("RESULT", {}).get("CODE", "")
        if code and code not in ("INFO-000", "INFO-200"):
            raise SeoulOpenApiError("서울 API가 요청을 거절했습니다.")
        return body

    async def _get(self, service: str, start: int, end: int, extra: str | None = None) -> dict:
        return await request_json(
            self.http(),
            base_url=self.settings.base_url,
            api_key=self.settings.api_key or "",
            service=service,
            start=start,
            end=end,
            extra=extra,
        )
