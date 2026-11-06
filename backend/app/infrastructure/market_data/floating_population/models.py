"""서울시 API 응답 한 행 → 파이썬 객체.

영문 컬럼명을 다루는 곳은 `from_api_row` 세 개뿐이다. 데이터셋이 개편되면 여기만 고친다.
(2026-09-07 실호출로 컬럼 일치 확인)
"""

from __future__ import annotations

import math
from datetime import date

from pydantic import BaseModel, ConfigDict

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


def _num(row: dict, key: str) -> float | None:
    """API·CSV의 빈 숫자를 None으로 정규화하며 실제 영값은 유지합니다."""
    v = row.get(key)
    if v is None or isinstance(v, str) and v.strip().lower() in {"", "null"}:
        return None
    return float(v)


def missing_fields(
    record: PopulationRecord | FlpopRecord, *, households: bool = False
) -> list[str]:
    """문자열 식별자는 제외하고 결측인 수치 경로만 반환합니다."""
    data = record.model_dump(exclude={"trdar_cd", "stdr_yyqu_cd"})
    if not households:
        data.pop("households", None)
    return [
        path
        for key, value in data.items()
        for path, number in (
            [(f"{key}/{part}", number) for part, number in value.items()]
            if isinstance(value, dict)
            else [(key, value)]
        )
        if number is None
    ]


def _trdar_code(row: dict) -> str:
    """누락된 코드를 문자열로 바꿔 정상 자료처럼 사용하지 않습니다."""
    value = row["TRDAR_CD"]
    code = str(value).strip() if value is not None else ""
    if not code:
        raise ValueError("상권코드가 누락되었습니다.")
    return code


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

    model_config = ConfigDict(allow_inf_nan=False)

    trdar_cd: str
    trdar_cd_nm: str
    x: float
    y: float
    relm_ar: float = 0.0
    trdar_se_nm: str | None = None
    adstrd_nm: str | None = None

    @property
    def equivalent_radius_m(self) -> float:
        """면적을 원으로 근사한 반지름. 상권 중위값 약 151m, 상위 10% 는 255m 이상."""
        return math.sqrt(self.relm_ar / math.pi) if self.relm_ar > 0 else 0.0

    @classmethod
    def from_api_row(cls, row: dict) -> TrdarArea:
        return cls(
            trdar_cd=_trdar_code(row),
            trdar_cd_nm=str(row.get("TRDAR_CD_NM") or "").strip(),
            x=float(row["XCNTS_VALUE"]),
            y=float(row["YDNTS_VALUE"]),
            relm_ar=_num(row, "RELM_AR") or 0.0,
            trdar_se_nm=str(row.get("TRDAR_SE_CD_NM") or "").strip() or None,
            adstrd_nm=str(row.get("ADSTRD_CD_NM") or "").strip() or None,
        )


class PopulationRecord(BaseModel):
    """주거인구(OA-15584)·직장인구(OA-15569) 한 행 = 한 상권 · 한 분기.

    두 데이터셋은 컬럼 이름의 가운데 토막만 다르다(`TOT_REPOP_CO` / `TOT_WRC_POPLTN_CO`).
    값은 통행량이 아니라 **사람 수**다. 가구 수는 주거인구에만 있다.
    (`APT_HSHLD_CO` 는 22개 분기 전 행이 0 이라 읽지 않는다 — 2026-09-20 전수 확인)
    """

    model_config = ConfigDict(allow_inf_nan=False)

    trdar_cd: str
    stdr_yyqu_cd: str
    total: float | None
    by_age: dict[str, float | None]
    households: float | None = None

    @staticmethod
    def _age_column(age: str, kind: str) -> str:
        return f"AGRDE_{age}_ABOVE_{kind}_CO" if age == "60" else f"AGRDE_{age}_{kind}_CO"

    @classmethod
    def columns(cls, kind: str) -> list[str]:
        """이 모델이 읽는 원자료 컬럼. 스냅샷 CSV 는 이 컬럼만 남긴다(`write_snapshot`)."""
        names = ["STDR_YYQU_CD", "TRDAR_CD", "TRDAR_CD_NM", f"TOT_{kind}_CO"]
        names += [cls._age_column(a, kind) for a in AGE_BANDS]
        return names + (["TOT_HSHLD_CO"] if kind == "REPOP" else [])

    @classmethod
    def from_api_row(cls, row: dict, kind: str) -> PopulationRecord:
        """`kind` 는 컬럼 가운데 토막 — 주거 `"REPOP"`, 직장 `"WRC_POPLTN"`.

        API 응답 행과 스냅샷 CSV 행(값이 문자열) 둘 다 받는다.
        """
        return cls(
            trdar_cd=_trdar_code(row),
            stdr_yyqu_cd=str(row["STDR_YYQU_CD"]),
            total=_num(row, f"TOT_{kind}_CO"),
            by_age={a: _num(row, cls._age_column(a, kind)) for a in AGE_BANDS},
            households=_num(row, "TOT_HSHLD_CO") if "TOT_HSHLD_CO" in row else None,
        )


class FlpopRecord(BaseModel):
    """길단위인구(OA-15568) 한 행 = 한 상권 · 한 분기."""

    model_config = ConfigDict(allow_inf_nan=False)

    trdar_cd: str
    stdr_yyqu_cd: str
    total: float | None
    male: float | None
    female: float | None
    by_time: dict[str, float | None]
    by_day: dict[str, float | None]
    by_age: dict[str, float | None]

    @classmethod
    def from_api_row(cls, row: dict) -> FlpopRecord:
        return cls(
            trdar_cd=_trdar_code(row),
            stdr_yyqu_cd=str(row["STDR_YYQU_CD"]),
            total=_num(row, "TOT_FLPOP_CO"),
            male=_num(row, "ML_FLPOP_CO"),
            female=_num(row, "FML_FLPOP_CO"),
            by_time={b: _num(row, f"TMZON_{b}_FLPOP_CO") for b in TIME_BANDS},
            by_day={d: _num(row, k) for d, k in _DAY_KEYS.items()},
            by_age={a: _num(row, k) for a, k in _AGE_KEYS.items()},
        )
