"""자료 출처와 기준 시점, 그리고 그 숫자를 읽는 법.

기준 시점은 **분기마다 갱신해야 하는 값**이라 한 곳에 모았다. 예전에는 `agent.py`가 조회일을
만들고 `config.py`가 연도를 따로 들고 있어서 서로 어긋날 수 있었다.

결정 에이전트 프롬프트가 "필드 이름, 설명, 단위와 실제 값을 함께 읽습니다"로 동작하므로,
`build_description()`이 만드는 문장도 여기 둔다 — 어느 자료를 어떤 단위로 읽는지가 출처와 한 몸이다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Settings

# ─────────────────────────────────────────────────────────────
# ⚠️ 분기마다 갱신하는 곳.
#    여기만 고치면 scope.period · data_reference_date · sources 가 함께 따라간다.
#
#    최신 분기는 공공데이터포털 파일데이터에서 확인한다.
#    상가정보 오픈API 응답에는 날짜 필드가 하나도 없어 API로는 알 수 없다.
#    https://www.data.go.kr/data/15083033/fileData.do
# ─────────────────────────────────────────────────────────────
SBIZ_PERIOD = "2026년 1분기"
SBIZ_REFERENCE_DATE = "2026-03-31"

LICENSE = "공공누리 출처표시"


@dataclass(frozen=True)
class DataSource:
    name: str
    url: str
    license: str
    period: str


SBIZ_SOURCE = DataSource(
    name="소상공인시장진흥공단 상가(상권)정보",
    url="https://www.data.go.kr/data/15012005/openapi.do",
    license=LICENSE,
    period=SBIZ_PERIOD,
)

FTC_SOURCE_NAME = "공정거래위원회 브랜드별 가맹점 현황"
FTC_SOURCE_URL = "https://www.data.go.kr/data/15110241/openapi.do"


def franchise_base_year(settings: Settings) -> int | None:
    """프랜차이즈 판정에 쓴 브랜드 목록의 기준 연도.

    `config`의 `ftc_year` 하나에서 파생시킨다 — 연도를 두 곳에 적으면 반드시 어긋난다.
    """
    try:
        return int(settings.ftc_year)
    except (TypeError, ValueError):
        return None


def build_sources(settings: Settings, *, with_franchise: bool) -> list[DataSource]:
    """실제로 쓴 자료만 출처에 싣는다. 공공누리 자료라 출처 표기가 의무다."""
    sources = [SBIZ_SOURCE]
    if with_franchise:
        year = franchise_base_year(settings)
        sources.append(
            DataSource(
                name=FTC_SOURCE_NAME,
                url=FTC_SOURCE_URL,
                license=LICENSE,
                period=f"{year}년" if year else settings.ftc_year,
            )
        )
    return sources


def build_description(
    settings: Settings,
    *,
    radius_m: int,
    store_total: int,
    baseline_radius_m: int | None,
    district_name: str | None,
    with_franchise: bool,
) -> str:
    """숫자의 기준과 단위를 글로 밝힌다.

    결정 에이전트가 필드 이름만 보고 단위를 추측하지 않도록, 배수의 분모가 무엇인지까지 적는다.
    """
    parts = [
        f"반경 {radius_m:,}m 안 점포 {store_total:,}개를 "
        f"{SBIZ_SOURCE.name} {SBIZ_PERIOD} 자료로 집계했습니다.",
        "밀도는 1km²당 점포 수, share·ratio는 0~1 비율, lq·lq_district는 배수로 1.0이 기준입니다.",
    ]

    if baseline_radius_m:
        parts.append(f"lq는 반경 {baseline_radius_m:,}m 안의 업종 비중과 비교한 값입니다.")
    if district_name:
        parts.append(f"lq_district는 {district_name} 전체와 비교한 값이라 lq와 분모가 다릅니다.")

    if with_franchise:
        year = franchise_base_year(settings)
        parts.append(
            f"프랜차이즈 비율은 공정거래위원회 {year}년 브랜드명과 상호명을 문자열로 대조한 결과라 "
            "누락과 오탐이 있고 confidence가 low입니다."
        )

    parts.append("업종을 추천하거나 점수를 매기지 않습니다. 판단은 결정 에이전트가 합니다.")
    return " ".join(parts)
