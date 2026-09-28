import uuid
from typing import Any

import pandas as pd

from app.industries import TAXONOMY
from app.industries.catalog import EXPECTED_INDUSTRY_COUNT

from .client import get_recent_quarters
from .config import Settings
from .scoring import (
    CLOSE_TREND_WEIGHT,
    NET_CHANGE_WEIGHT,
    RECENT_CLOSE_RATE_WEIGHT,
    TURNOVER_WEIGHT,
    score_business_lifecycle,
)


def to_int(value: Any) -> int | None:
    """
    pandas NaN 값을 JSON의 null로 변환하기 위한 함수.
    """
    if pd.isna(value):
        return None

    return int(value)


def to_float(value: Any) -> float | None:
    """
    pandas NaN 값을 JSON의 null로 변환하기 위한 함수.
    """
    if pd.isna(value):
        return None

    return round(float(value), 2)


def get_score_missing_reason(
    row: pd.Series,
    quarter_count: int,
) -> str:
    """
    Lifecycle Score를 계산하지 못한 이유를 정리한다.
    """

    # ========================================================
    # 1. 서울시 데이터 자체가 없는 경우
    # ========================================================

    if not bool(row["data_available"]) or not bool(row["data_complete"]):
        missing_reason = row.get("missing_reason")

        if pd.isna(missing_reason):
            return "분석 가능한 개폐업 데이터가 없습니다."

        return str(missing_reason)

    # ========================================================
    # 2. 데이터는 있지만 충분한 기간이 없는 경우
    # ========================================================

    observed_quarters = row.get("observed_quarters")

    if pd.notna(observed_quarters) and int(observed_quarters) < quarter_count:
        return (
            f"최근 {quarter_count}개 분기 중 "
            f"{int(observed_quarters)}개 분기에만 데이터가 있어 "
            "안정적인 추세 점수를 계산하기 어렵습니다."
        )

    # ========================================================
    # 3. 최근 1년 지표 부족
    # ========================================================

    if pd.isna(row.get("recent_year_close_rate")):
        return "최근 1년 폐업률을 계산하기 위한 데이터가 부족합니다."

    # ========================================================
    # 4. 장기 추세 지표 부족
    # ========================================================

    if pd.isna(row.get("close_rate_trend")):
        return "과거 대비 최근 폐업률 변화를 계산하기 위한 데이터가 부족합니다."

    return "Lifecycle Score 계산에 필요한 데이터가 부족합니다."


def build_agent_input(
    area_code: str,
    base_quarter: str,
    quarter_count: int = 12,
    request_id: str | None = None,
    area_name: str | None = None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    서울시 API 조회 → 전처리 → 점수 계산 결과를 이용해
    Business Lifecycle Agent 입력 JSON을 생성한다.
    """

    # ========================================================
    # 1. Lifecycle Score 계산
    #
    # scoring.py
    #   → preprocess.py
    #       → client.py
    #
    # 순서로 자동 호출된다.
    # ========================================================

    df = score_business_lifecycle(
        area_code=area_code,
        base_quarter=base_quarter,
        quarter_count=quarter_count,
        settings=settings,
    )

    # ========================================================
    # 2. 실제 분석 기간 확인
    # ========================================================

    quarters = get_recent_quarters(
        base_quarter=base_quarter,
        count=quarter_count,
    )

    # ========================================================
    # 3. 점수 계산 가능한 업종
    # ========================================================

    scored_df = df[df["lifecycle_score"].notna()].copy()

    # ========================================================
    # 4. 판단 보류 업종
    # ========================================================

    unscored_df = df[df["lifecycle_score"].isna()].copy()

    industries: list[dict[str, Any]] = []

    # ========================================================
    # 5. 점수 해석과 관측 자료 활용을 구분해 업종 입력 구성
    # ========================================================

    partial_industries: list[dict[str, Any]] = []
    unavailable_industries: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        score_available = pd.notna(row["lifecycle_score"])
        analysis_available = (
            bool(row["data_available"])
            and row["data_status"] != "unsupported"
            and row["observed_quarters"] >= 2
        )
        industry = {
            "industry_id": str(row["service_id"]),
            "industry_name": str(row["service_name"]),
            "data_available": bool(row["data_available"]),
            "analysis_available": analysis_available,
            "score_available": score_available,
            "data_status": row["data_status"],
            "data_complete": bool(row["data_complete"]),
            "observed_quarters": to_int(row["observed_quarters"]),
            "source_coverage": {
                "expected_quarters": quarter_count,
                **{
                    key: to_int(row[key])
                    for key in (
                        "observed_quarters",
                        "complete_quarters",
                        "expected_source_count",
                        "observed_source_rows",
                        "expected_source_rows",
                        "recent_year_observed_quarters",
                        "oldest_year_observed_quarters",
                    )
                },
                "observed_source_count": to_int(row["source_industry_count"]),
                "observed_quarter_codes": row["observed_quarter_codes"],
                "quarterly_source_ids": row["quarterly_source_ids"],
            },
            # =================================================
            # 실제 개폐업 데이터
            # =================================================
            "metrics": {
                # 데이터 확보 정도
                "observed_quarters": to_int(row["observed_quarters"]),
                # 현재 규모
                "latest_store_count": to_int(row["latest_store_count"]),
                "avg_store_count": to_float(row["avg_store_count"]),
                # 전체 분석기간
                "period_open_count": to_int(row["period_open_count"]),
                "period_close_count": to_int(row["period_close_count"]),
                "period_net_change": to_int(row["period_net_change"]),
                "avg_open_rate": to_float(row["avg_open_rate"]),
                "avg_close_rate": to_float(row["avg_close_rate"]),
                "net_change_rate": to_float(row["net_change_rate"]),
                "turnover_rate": to_float(row["turnover_rate"]),
                # 최근 1년
                "recent_year_open_count": to_int(row["recent_year_open_count"]),
                "recent_year_close_count": to_int(row["recent_year_close_count"]),
                "recent_year_net_change": to_int(row["recent_year_net_change"]),
                "recent_year_close_rate": to_float(row["recent_year_close_rate"]),
                "recent_year_net_change_rate": to_float(row["recent_year_net_change_rate"]),
                # 과거와 최근의 비교
                "oldest_year_close_rate": to_float(row["oldest_year_close_rate"]),
                "close_rate_trend": to_float(row["close_rate_trend"]),
            },
            # =================================================
            # Python에서 계산한 상대평가 점수
            # =================================================
            "component_scores": {
                "recent_close_rate_score": to_float(row["recent_close_rate_score"]),
                "net_change_score": to_float(row["net_change_score"]),
                "turnover_score": to_float(row["turnover_score"]),
                "close_trend_score": to_float(row["close_trend_score"]),
            },
            "lifecycle_score": to_float(row["lifecycle_score"]),
            # 점수 없는 관측 자료는 기간·원천 누락을 고려해 보수적으로 해석합니다.
            "confidence": (
                str(row["confidence"])
                if score_available
                else "low"
                if analysis_available
                else "none"
            ),
        }

        if score_available:
            industries.append(industry)
        else:
            reason = get_score_missing_reason(row, quarter_count)
            if analysis_available:
                reason += " Lifecycle Score 없이 실제 관측 지표만 참고할 수 있습니다."
            elif row["data_available"]:
                reason += " 실제 관측이 2분기 미만이므로 개폐업 판단 근거로 사용하지 않습니다."
            industry["missing_reason"] = reason
            (partial_industries if analysis_available else unavailable_industries).append(industry)

    # ========================================================
    # 7. Agent 입력 JSON
    # ========================================================

    agent_input: dict[str, Any] = {
        "request_id": request_id or str(uuid.uuid4()),
        "analysis_type": "business_lifecycle",
        "taxonomy": dict(TAXONOMY),
        "scope": {
            "area_code": area_code,
            "area_name": area_name,
            "base_quarter": base_quarter,
            "period": {
                "start_quarter": quarters[0],
                "end_quarter": quarters[-1],
                "quarter_count": quarter_count,
            },
        },
        # ====================================================
        # 점수 계산 방식 설명
        # ====================================================
        "scoring_method": {
            "score_type": "relative",
            "description": (
                "최근 개폐업 데이터와 폐업률 변화 추세를 "
                "기반으로 분석 가능한 업종끼리 상대 비교한 "
                "Lifecycle Score"
            ),
            "weights": {
                "recent_year_close_rate": (RECENT_CLOSE_RATE_WEIGHT),
                "net_change_rate": (NET_CHANGE_WEIGHT),
                "turnover_stability": (TURNOVER_WEIGHT),
                "close_rate_trend": (CLOSE_TREND_WEIGHT),
            },
            "notes": [
                ("lifecycle_score는 미래 생존확률이 아니다."),
                ("lifecycle_score는 분석 가능한 업종끼리 상대 비교한 점수이다."),
                ("최근 1년 폐업률은 낮을수록 긍정적으로 평가한다."),
                ("전체 분석기간 순증감률은 높을수록 긍정적으로 평가한다."),
                ("회전율은 낮을수록 안정적으로 평가한다."),
                ("close_rate_trend가 음수이면 과거보다 최근 폐업률이 낮아진 것이다."),
                ("close_rate_trend가 양수이면 과거보다 최근 폐업률이 높아진 것이다."),
                (
                    "불완전 자료의 metrics는 실제 관측 분기·원본업종만 집계한다. "
                    "avg_store_count의 분모는 관측 분기 수이며, 비율은 관측 건수 합계와 "
                    "같은 범위의 점포 수 합계로 계산한다. 최근·과거 1년 지표도 "
                    "각 4분기 구간 중 관측된 자료만 사용하므로 source_coverage를 확인한다."
                ),
                ("누락 분기·원본업종·건수는 0으로 보정하지 않으며 결측 지표는 null이다."),
            ],
        },
        # ====================================================
        # Coverage
        # ====================================================
        "coverage": {
            "target_industries": EXPECTED_INDUSTRY_COUNT,
            "scored_industries": len(scored_df),
            "unscored_industries": len(unscored_df),
            "partial_industries": len(partial_industries),
            "available_industries": len(industries) + len(partial_industries),
            "unavailable_industries": len(unavailable_industries),
        },
        # LLM 분석 대상
        "industries": industries,
        # 점수 없이 중재 Agent에 직접 전달할 관측 자료
        "partial_industries": partial_industries,
        # 판단 보류 대상
        "unavailable_industries": (unavailable_industries),
    }

    return agent_input
