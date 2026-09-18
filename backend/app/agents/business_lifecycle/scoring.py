import pandas as pd

from .config import Settings
from .preprocess import preprocess_business_lifecycle_data

# ============================================================
# Lifecycle Score 가중치
# ============================================================

RECENT_CLOSE_RATE_WEIGHT = 0.35
NET_CHANGE_WEIGHT = 0.25
TURNOVER_WEIGHT = 0.20
CLOSE_TREND_WEIGHT = 0.20


def get_confidence(
    observed_quarters: float,
    avg_store_count: float,
    expected_quarters: int,
) -> str:
    """
    데이터 기간과 평균 점포 수를 함께 고려한 신뢰도.

    현재 기준은 MVP용 자체 규칙이며
    공식 통계 기준은 아니다.
    """

    if pd.isna(observed_quarters) or pd.isna(avg_store_count):
        return "none"

    coverage_ratio = observed_quarters / expected_quarters

    if coverage_ratio >= 1.0 and avg_store_count >= 20:
        return "high"

    if coverage_ratio >= 0.67 and avg_store_count >= 5:
        return "medium"

    return "low"


def calculate_lifecycle_scores(
    df: pd.DataFrame,
    quarter_count: int = 12,
) -> pd.DataFrame:
    """
    전처리된 3년 개폐업 데이터를 기반으로
    업종 간 상대 Lifecycle Score를 계산한다.
    """

    result_df = df.copy()

    # ========================================================
    # 1. 점수 계산 가능한 업종 선택
    # ========================================================

    score_mask = (
        result_df["data_available"]
        & result_df["data_complete"]
        & result_df["recent_year_close_rate"].notna()
        & result_df["net_change_rate"].notna()
        & result_df["turnover_rate"].notna()
        & result_df["close_rate_trend"].notna()
    )

    score_df = result_df.loc[score_mask].copy()

    # ========================================================
    # 2. 최근 1년 폐업률 안정성
    #
    # 낮을수록 높은 점수
    # ========================================================

    score_df["recent_close_rate_score"] = (
        score_df["recent_year_close_rate"].rank(
            method="average",
            pct=True,
            ascending=False,
        )
        * 100
    )

    # ========================================================
    # 3. 최근 3년 순증감률
    #
    # 높을수록 높은 점수
    # ========================================================

    score_df["net_change_score"] = (
        score_df["net_change_rate"].rank(
            method="average",
            pct=True,
            ascending=True,
        )
        * 100
    )

    # ========================================================
    # 4. 최근 3년 회전 안정성
    #
    # turnover_rate가 낮을수록
    # 개폐업 교체가 덜 빈번하다고 판단
    # ========================================================

    score_df["turnover_score"] = (
        score_df["turnover_rate"].rank(
            method="average",
            pct=True,
            ascending=False,
        )
        * 100
    )

    # ========================================================
    # 5. 폐업률 변화 점수
    #
    # close_rate_trend
    # = 최근 1년 폐업률 - 가장 오래된 1년 폐업률
    #
    # 값이 낮을수록 좋음
    #
    # -5 → 폐업률 감소
    # +5 → 폐업률 증가
    # ========================================================

    score_df["close_trend_score"] = (
        score_df["close_rate_trend"].rank(
            method="average",
            pct=True,
            ascending=False,
        )
        * 100
    )

    # ========================================================
    # 6. Lifecycle Score
    # ========================================================

    score_df["lifecycle_score"] = (
        RECENT_CLOSE_RATE_WEIGHT * score_df["recent_close_rate_score"]
        + NET_CHANGE_WEIGHT * score_df["net_change_score"]
        + TURNOVER_WEIGHT * score_df["turnover_score"]
        + CLOSE_TREND_WEIGHT * score_df["close_trend_score"]
    )

    score_columns = [
        "recent_close_rate_score",
        "net_change_score",
        "turnover_score",
        "close_trend_score",
        "lifecycle_score",
    ]

    score_df[score_columns] = score_df[score_columns].round(1)

    # ========================================================
    # 7. Confidence
    # ========================================================

    score_df["confidence"] = score_df.apply(
        lambda row: get_confidence(
            observed_quarters=row["observed_quarters"],
            avg_store_count=row["avg_store_count"],
            expected_quarters=quarter_count,
        ),
        axis=1,
    )

    # ========================================================
    # 8. 공통 75개 Master에 점수 다시 결합
    # ========================================================

    score_result = score_df[
        [
            "service_id",
            "recent_close_rate_score",
            "net_change_score",
            "turnover_score",
            "close_trend_score",
            "lifecycle_score",
            "confidence",
        ]
    ].copy()

    final_df = result_df.merge(
        score_result,
        on="service_id",
        how="left",
    )

    final_df["confidence"] = final_df["confidence"].fillna("none")

    return final_df


def score_business_lifecycle(
    area_code: str,
    base_quarter: str,
    quarter_count: int = 12,
    *,
    settings: Settings | None = None,
) -> pd.DataFrame:
    """
    API 조회 → 전처리 → 점수 계산까지 실행한다.
    """

    preprocessed_df = preprocess_business_lifecycle_data(
        area_code=area_code,
        base_quarter=base_quarter,
        quarter_count=quarter_count,
        settings=settings,
    )

    return calculate_lifecycle_scores(
        df=preprocessed_df,
        quarter_count=quarter_count,
    )
