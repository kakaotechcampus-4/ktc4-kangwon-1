"""서울시 API 응답 한 행 → 파이썬 객체.

영문 컬럼명을 다루는 곳은 `from_api_row` 두 개뿐이다. 데이터셋이 개편되면 여기만 고친다.
(2026-09-07 실호출로 컬럼 일치 확인)
"""

from __future__ import annotations

import math
from datetime import date

from pydantic import BaseModel

TIME_BANDS = ("00_06", "06_11", "11_14", "14_17", "17_21", "21_24")
# 구간 길이가 3~6시간으로 다르다. 총량을 그대로 비교하면 6시간짜리 00~06시가 거의 항상 1위가 되므로
# 시간대 비교는 반드시 시간당 값으로 한다 (실데이터에서 확인된 왜곡).
TIME_BAND_HOURS = {"00_06": 6, "06_11": 5, "11_14": 3, "14_17": 3, "17_21": 4, "21_24": 3}
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri")
WEEKEND = ("sat", "sun")
AGE_BANDS = ("10", "20", "30", "40", "50", "60")

_DAY_KEYS = {
    "mon": "MON_FLPOP_CO",
    "tue": "TUES_FLPOP_CO",
    "wed": "WED_FLPOP_CO",
    "thu": "THUR_FLPOP_CO",
    "fri": "FRI_FLPOP_CO",
    "sat": "SAT_FLPOP_CO",
    "sun": "SUN_FLPOP_CO",
}
_AGE_KEYS = {
    "10": "AGRDE_10_FLPOP_CO",
    "20": "AGRDE_20_FLPOP_CO",
    "30": "AGRDE_30_FLPOP_CO",
    "40": "AGRDE_40_FLPOP_CO",
    "50": "AGRDE_50_FLPOP_CO",
    "60": "AGRDE_60_ABOVE_FLPOP_CO",
}


def _num(row: dict, key: str) -> float:
    v = row.get(key)
    return 0.0 if v in (None, "") else float(v)


def period_ko(stdr_yyqu_cd: str) -> str:
    """'20262' → '2026년 2분기' (계약 scope.period 형식)."""
    return f"{stdr_yyqu_cd[:4]}년 {stdr_yyqu_cd[4]}분기"


def quarter_days(stdr_yyqu_cd: str) -> int:
    """'20262' → 그 분기의 일수(91). 분기 합계를 일평균으로 바꿀 때 쓴다.

    이 데이터의 total·by_age·by_time·by_day 는 모두 **분기 합계**다(by_day 합계가 total 과
    같은 것으로 확인). 결정 에이전트에 넘길 때 일평균을 함께 주려면 정확한 일수가 필요하다.
    """
    year, quarter = int(stdr_yyqu_cd[:4]), int(stdr_yyqu_cd[4])
    start = date(year, 3 * quarter - 2, 1)
    end = date(year + 1, 1, 1) if quarter == 4 else date(year, 3 * quarter + 1, 1)
    return (end - start).days


class TrdarArea(BaseModel):
    """상권영역(OA-15560) 한 행. 좌표는 EPSG:5181(미터).

    x/y 는 상권 구역의 **대표 점 하나**다 — API 가 폴리곤을 주지 않는다. 대신 면적(`relm_ar`)
    은 주므로, 상권이 얼마나 큰 구역인지는 `equivalent_radius_m` 로 가늠할 수 있다.
    """

    trdar_cd: str
    trdar_cd_nm: str
    x: float
    y: float
    relm_ar: float = 0.0
    trdar_se_nm: str | None = None
    signgu_nm: str | None = None
    adstrd_nm: str | None = None

    @property
    def equivalent_radius_m(self) -> float:
        """면적을 원으로 근사한 반지름. 상권 중위값 약 151m, 상위 10% 는 255m 이상."""
        return math.sqrt(self.relm_ar / math.pi) if self.relm_ar > 0 else 0.0

    @classmethod
    def from_api_row(cls, row: dict) -> TrdarArea:
        return cls(
            trdar_cd=str(row["TRDAR_CD"]),
            trdar_cd_nm=str(row.get("TRDAR_CD_NM", "")),
            x=float(row["XCNTS_VALUE"]),
            y=float(row["YDNTS_VALUE"]),
            relm_ar=_num(row, "RELM_AR"),
            trdar_se_nm=row.get("TRDAR_SE_CD_NM"),
            signgu_nm=row.get("SIGNGU_CD_NM"),
            adstrd_nm=row.get("ADSTRD_CD_NM"),
        )


class FlpopRecord(BaseModel):
    """길단위인구(OA-15568) 한 행 = 한 상권 · 한 분기."""

    trdar_cd: str
    stdr_yyqu_cd: str
    total: float
    male: float
    female: float
    by_time: dict[str, float]
    by_day: dict[str, float]
    by_age: dict[str, float]

    @classmethod
    def from_api_row(cls, row: dict) -> FlpopRecord:
        return cls(
            trdar_cd=str(row["TRDAR_CD"]),
            stdr_yyqu_cd=str(row["STDR_YYQU_CD"]),
            total=_num(row, "TOT_FLPOP_CO"),
            male=_num(row, "ML_FLPOP_CO"),
            female=_num(row, "FML_FLPOP_CO"),
            by_time={b: _num(row, f"TMZON_{b}_FLPOP_CO") for b in TIME_BANDS},
            by_day={d: _num(row, k) for d, k in _DAY_KEYS.items()},
            by_age={a: _num(row, k) for a, k in _AGE_KEYS.items()},
        )
