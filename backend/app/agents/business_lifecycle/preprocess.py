import argparse
from pathlib import Path

import pandas as pd

from .client import fetch_recent_store_data, get_recent_quarters
from .mapping import (
    EXCLUDED_SEOUL_INDUSTRIES,
    SEOUL_TO_SERVICE,
    SERVICE_INDUSTRIES,
    UNSUPPORTED_SERVICE_INDUSTRIES,
)


def calculate_rate(
    numerator: float,
    denominator: float,
) -> float | None:
    """분자 / 분모 * 100 계산."""
    if denominator <= 0:
        return None

    return round(
        numerator / denominator * 100,
        2,
    )


def preprocess_business_lifecycle_data(
    area_code: str,
    base_quarter: str,
    quarter_count: int = 12,
) -> pd.DataFrame:
    """
    서울시 Open API에서 최근 N개 분기의 개폐업 데이터를 가져와
    우리 서비스 70개 업종 기준으로 전처리한다.

    Parameters
    ----------
    area_code:
        서울시 상권코드.
        예: 3120240

    base_quarter:
        분석 기준 분기.
        예: 20252

    quarter_count:
        사용할 최근 분기 수.
        기본값은 12개 분기 = 3년.

    Returns
    -------
    pd.DataFrame
        서비스 70개 업종 기준 전처리 결과.
    """

    # ========================================================
    # 1. 분석 대상 분기 생성
    # ========================================================

    quarters = get_recent_quarters(
        base_quarter=base_quarter,
        count=quarter_count,
    )

    print("===== 분석 기간 =====")
    print("상권 코드:", area_code)
    print("기준 분기:", base_quarter)
    print("분기 수:", len(quarters))
    print("분기:", ", ".join(quarters))

    # ========================================================
    # 2. 서울시 Open API에서 데이터 조회
    # ========================================================

    rows = fetch_recent_store_data(
        area_code=area_code,
        base_quarter=base_quarter,
        quarter_count=quarter_count,
    )

    if not rows:
        raise ValueError("서울시 Open API에서 조회된 데이터가 없습니다.")

    df = pd.DataFrame(rows)

    print()
    print("API 원본 행 수:", len(df))

    # ========================================================
    # 3. 숫자 컬럼 정리
    # ========================================================

    numeric_columns = [
        "similr_induty_stor_co",
        "stor_co",
        "frc_stor_co",
        "opbiz_rt",
        "opbiz_stor_co",
        "clsbiz_rt",
        "clsbiz_stor_co",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        ).fillna(0)

    df["stdr_yyqu_cd"] = df["stdr_yyqu_cd"].astype(str)

    df["svc_induty_cd"] = df["svc_induty_cd"].astype(str)

    # ========================================================
    # 4. 서울시 업종 → 서비스 70개 업종 매핑
    # ========================================================

    df["service_id"] = df["svc_induty_cd"].map(SEOUL_TO_SERVICE)

    excluded_mask = df["svc_induty_cd"].isin(EXCLUDED_SEOUL_INDUSTRIES.keys())

    unknown_mask = df["service_id"].isna() & ~excluded_mask

    unknown_df = df[unknown_mask]

    if not unknown_df.empty:
        unknown_codes = sorted(unknown_df["svc_induty_cd"].unique())

        raise ValueError(f"mapping.py에 정의되지 않은 서울시 업종이 있습니다: {unknown_codes}")

    # 전자상거래업 등 의도적으로 제외한 업종 제거
    mapped_df = df[df["service_id"].notna()].copy()

    mapped_df["service_id"] = mapped_df["service_id"].astype(int)

    mapped_df["service_name"] = mapped_df["service_id"].map(SERVICE_INDUSTRIES)

    print(
        "매핑 후 원본 행 수:",
        len(mapped_df),
    )

    # ========================================================
    # 5. 분기별로 통합 70개 업종 집계
    #
    # 예:
    # 패스트푸드점 + 치킨전문점
    # → 패스트푸드·치킨전문점
    # ========================================================

    quarterly_df = mapped_df.groupby(
        [
            "stdr_yyqu_cd",
            "service_id",
            "service_name",
        ],
        as_index=False,
    ).agg(
        store_count=(
            "similr_induty_stor_co",
            "sum",
        ),
        open_count=(
            "opbiz_stor_co",
            "sum",
        ),
        close_count=(
            "clsbiz_stor_co",
            "sum",
        ),
    )

    # ========================================================
    # 6. 3년 전체 집계
    # ========================================================

    period_df = quarterly_df.groupby(
        [
            "service_id",
            "service_name",
        ],
        as_index=False,
    ).agg(
        observed_quarters=(
            "stdr_yyqu_cd",
            "nunique",
        ),
        # 각 분기의 점포 수 합
        # 비율 계산 시 가중 분모로 사용
        store_exposure=(
            "store_count",
            "sum",
        ),
        avg_store_count=(
            "store_count",
            "mean",
        ),
        period_open_count=(
            "open_count",
            "sum",
        ),
        period_close_count=(
            "close_count",
            "sum",
        ),
    )

    period_df["period_net_change"] = (
        period_df["period_open_count"] - period_df["period_close_count"]
    )

    # ========================================================
    # 7. 3년 전체 개폐업 비율
    #
    # 각 분기 비율을 단순 평균하지 않고
    # 점포 수를 분모로 가중 계산
    # ========================================================

    period_df["avg_open_rate"] = period_df.apply(
        lambda row: calculate_rate(
            row["period_open_count"],
            row["store_exposure"],
        ),
        axis=1,
    )

    period_df["avg_close_rate"] = period_df.apply(
        lambda row: calculate_rate(
            row["period_close_count"],
            row["store_exposure"],
        ),
        axis=1,
    )

    period_df["net_change_rate"] = period_df.apply(
        lambda row: calculate_rate(
            row["period_net_change"],
            row["store_exposure"],
        ),
        axis=1,
    )

    period_df["turnover_rate"] = (period_df["avg_open_rate"] + period_df["avg_close_rate"]).round(2)

    # ========================================================
    # 8. 최근 1년 데이터
    #
    # 12개 분기 중 마지막 4개 분기
    # ========================================================

    recent_quarters = quarters[-4:]

    recent_df = quarterly_df[quarterly_df["stdr_yyqu_cd"].isin(recent_quarters)]

    recent_summary = recent_df.groupby(
        "service_id",
        as_index=False,
    ).agg(
        recent_store_exposure=(
            "store_count",
            "sum",
        ),
        recent_year_open_count=(
            "open_count",
            "sum",
        ),
        recent_year_close_count=(
            "close_count",
            "sum",
        ),
    )

    recent_summary["recent_year_net_change"] = (
        recent_summary["recent_year_open_count"] - recent_summary["recent_year_close_count"]
    )

    recent_summary["recent_year_close_rate"] = recent_summary.apply(
        lambda row: calculate_rate(
            row["recent_year_close_count"],
            row["recent_store_exposure"],
        ),
        axis=1,
    )

    recent_summary["recent_year_net_change_rate"] = recent_summary.apply(
        lambda row: calculate_rate(
            row["recent_year_net_change"],
            row["recent_store_exposure"],
        ),
        axis=1,
    )

    # ========================================================
    # 9. 가장 오래된 1년 데이터
    #
    # 추세 비교용: 첫 4개 분기
    # ========================================================

    oldest_quarters = quarters[:4]

    oldest_df = quarterly_df[quarterly_df["stdr_yyqu_cd"].isin(oldest_quarters)]

    oldest_summary = oldest_df.groupby(
        "service_id",
        as_index=False,
    ).agg(
        oldest_store_exposure=(
            "store_count",
            "sum",
        ),
        oldest_year_close_count=(
            "close_count",
            "sum",
        ),
    )

    oldest_summary["oldest_year_close_rate"] = oldest_summary.apply(
        lambda row: calculate_rate(
            row["oldest_year_close_count"],
            row["oldest_store_exposure"],
        ),
        axis=1,
    )

    # ========================================================
    # 10. 최근 1년 vs 가장 오래된 1년 폐업률 변화
    #
    # 음수 → 최근 폐업률이 더 낮음
    # 양수 → 최근 폐업률이 더 높음
    # ========================================================

    period_df = period_df.merge(
        recent_summary,
        on="service_id",
        how="left",
    )

    period_df = period_df.merge(
        oldest_summary[
            [
                "service_id",
                "oldest_year_close_rate",
            ]
        ],
        on="service_id",
        how="left",
    )

    period_df["close_rate_trend"] = (
        period_df["recent_year_close_rate"] - period_df["oldest_year_close_rate"]
    ).round(2)

    # ========================================================
    # 11. 기준분기 최신 점포 수
    # ========================================================

    latest_df = quarterly_df[quarterly_df["stdr_yyqu_cd"] == base_quarter][
        [
            "service_id",
            "store_count",
        ]
    ].copy()

    latest_df = latest_df.rename(columns={"store_count": "latest_store_count"})

    period_df = period_df.merge(
        latest_df,
        on="service_id",
        how="left",
    )

    # ========================================================
    # 12. 원본 서울시 업종 정보
    # ========================================================

    source_info = mapped_df.groupby(
        "service_id",
        as_index=False,
    ).agg(
        source_industry_count=(
            "svc_induty_cd",
            "nunique",
        ),
        source_industries=(
            "svc_induty_cd_nm",
            lambda values: " | ".join(sorted(set(values))),
        ),
    )

    period_df = period_df.merge(
        source_info,
        on="service_id",
        how="left",
    )

    # ========================================================
    # 13. 서비스 70개 Master
    # ========================================================

    master_df = pd.DataFrame(
        [
            {
                "service_id": service_id,
                "service_name": service_name,
            }
            for service_id, service_name in SERVICE_INDUSTRIES.items()
        ]
    )

    final_df = master_df.merge(
        period_df,
        on=[
            "service_id",
            "service_name",
        ],
        how="left",
    )

    # ========================================================
    # 14. 데이터 존재 여부
    # ========================================================

    final_df["data_available"] = final_df["observed_quarters"].notna()

    def get_missing_reason(
        row: pd.Series,
    ) -> str | None:
        if row["data_available"]:
            return None

        service_id = int(row["service_id"])

        if service_id in UNSUPPORTED_SERVICE_INDUSTRIES:
            return "서울시 생활밀접업종 데이터에 직접 대응 업종 없음"

        return f"최근 {quarter_count}개 분기에 대응 서울시 업종 데이터 없음"

    final_df["missing_reason"] = final_df.apply(
        get_missing_reason,
        axis=1,
    )

    # ========================================================
    # 15. 소수점 정리
    # ========================================================

    round_columns = [
        "avg_store_count",
        "avg_open_rate",
        "avg_close_rate",
        "net_change_rate",
        "turnover_rate",
        "recent_year_close_rate",
        "recent_year_net_change_rate",
        "oldest_year_close_rate",
        "close_rate_trend",
    ]

    for column in round_columns:
        final_df[column] = final_df[column].round(2)

    # ========================================================
    # 16. 컬럼 순서
    # ========================================================

    final_df = final_df[
        [
            "service_id",
            "service_name",
            "data_available",
            "observed_quarters",
            "latest_store_count",
            "avg_store_count",
            # 3년 전체
            "period_open_count",
            "period_close_count",
            "period_net_change",
            "avg_open_rate",
            "avg_close_rate",
            "net_change_rate",
            "turnover_rate",
            # 최근 1년
            "recent_year_open_count",
            "recent_year_close_count",
            "recent_year_net_change",
            "recent_year_close_rate",
            "recent_year_net_change_rate",
            # 과거 대비 변화
            "oldest_year_close_rate",
            "close_rate_trend",
            # 매핑 확인
            "source_industry_count",
            "source_industries",
            "missing_reason",
        ]
    ]

    return final_df


def main() -> None:
    parser = argparse.ArgumentParser(description=("서울시 Open API 기반 Business Lifecycle 전처리"))

    parser.add_argument(
        "--area-code",
        required=True,
    )

    parser.add_argument(
        "--base-quarter",
        required=True,
    )

    parser.add_argument(
        "--count",
        type=int,
        default=12,
    )

    parser.add_argument(
        "--output",
        help=("테스트 결과를 저장할 CSV 경로. 생략하면 파일을 생성하지 않습니다."),
    )

    args = parser.parse_args()

    result_df = preprocess_business_lifecycle_data(
        area_code=args.area_code,
        base_quarter=args.base_quarter,
        quarter_count=args.count,
    )

    print()
    print("===== 전처리 결과 =====")
    print("서비스 전체 업종:", len(result_df))

    print(
        "데이터 존재 업종:",
        int(result_df["data_available"].sum()),
    )

    print(
        "데이터 없는 업종:",
        int((~result_df["data_available"]).sum()),
    )

    print()
    print("샘플 결과:")

    print(result_df[result_df["data_available"]].head(10).to_string(index=False))

    if args.output:
        output_path = Path(args.output)

        result_df.to_csv(
            output_path,
            index=False,
            encoding="utf-8-sig",
        )

        print()
        print(
            "테스트 CSV 저장 완료:",
            output_path,
        )


if __name__ == "__main__":
    main()
