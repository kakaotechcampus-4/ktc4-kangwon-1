import argparse
import json
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from .client import get_recent_quarters
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

    if not bool(row["data_available"]):
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
    # 5. LLM이 실제로 분석할 업종
    # ========================================================

    for _, row in scored_df.iterrows():
        industry = {
            "industry_id": to_int(row["service_id"]),
            "industry_name": str(row["service_name"]),
            "data_available": True,
            "score_available": True,
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
            "confidence": str(row["confidence"]),
        }

        industries.append(industry)

    # ========================================================
    # 6. 판단 보류 업종
    #
    # 이 업종들은 LLM 분석 대상에서 제외한다.
    # ========================================================

    unavailable_industries: list[dict[str, Any]] = []

    for _, row in unscored_df.iterrows():
        unavailable_industries.append(
            {
                "industry_id": to_int(row["service_id"]),
                "industry_name": str(row["service_name"]),
                "data_available": bool(row["data_available"]),
                "score_available": False,
                "observed_quarters": to_int(row.get("observed_quarters")),
                "lifecycle_score": None,
                "confidence": "none",
                "missing_reason": (
                    get_score_missing_reason(
                        row=row,
                        quarter_count=quarter_count,
                    )
                ),
            }
        )

    # ========================================================
    # 7. Agent 입력 JSON
    # ========================================================

    agent_input: dict[str, Any] = {
        "request_id": request_id or str(uuid.uuid4()),
        "analysis_type": "business_lifecycle",
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
            ],
        },
        # ====================================================
        # Coverage
        # ====================================================
        "coverage": {
            "target_industries": 70,
            "scored_industries": len(scored_df),
            "unscored_industries": len(unscored_df),
        },
        # LLM 분석 대상
        "industries": industries,
        # 판단 보류 대상
        "unavailable_industries": (unavailable_industries),
    }

    return agent_input


def main() -> None:
    parser = argparse.ArgumentParser(description=("Business Lifecycle Agent 입력 JSON 생성"))

    parser.add_argument(
        "--area-code",
        required=True,
        help="서울시 상권코드",
    )

    parser.add_argument(
        "--base-quarter",
        required=True,
        help="기준 분기. 예: 20252",
    )

    parser.add_argument(
        "--count",
        type=int,
        default=12,
        help="분석할 분기 수. 기본값 12",
    )

    parser.add_argument(
        "--output",
        help=("테스트용 JSON 저장 경로. 생략하면 파일을 저장하지 않습니다."),
    )

    args = parser.parse_args()

    agent_input = build_agent_input(
        area_code=args.area_code,
        base_quarter=args.base_quarter,
        quarter_count=args.count,
    )

    # ========================================================
    # 테스트 출력
    # ========================================================

    coverage = agent_input["coverage"]
    period = agent_input["scope"]["period"]

    print()
    print("===== Agent Input 생성 결과 =====")

    print(
        "전체 목표 업종:",
        coverage["target_industries"],
    )

    print(
        "점수 계산 업종:",
        coverage["scored_industries"],
    )

    print(
        "판단 보류 업종:",
        coverage["unscored_industries"],
    )

    print(
        "분석 시작 분기:",
        period["start_quarter"],
    )

    print(
        "분석 종료 분기:",
        period["end_quarter"],
    )

    print(
        "분석 분기 수:",
        period["quarter_count"],
    )

    # 70개가 제대로 유지되는지 확인
    assert coverage["scored_industries"] + coverage["unscored_industries"] == 70

    # ========================================================
    # 테스트용 JSON 저장
    # ========================================================

    if args.output:
        output_path = Path(args.output)

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                agent_input,
                file,
                ensure_ascii=False,
                indent=2,
            )

        print()
        print(
            "Agent Input JSON 저장 완료:",
            output_path,
        )


if __name__ == "__main__":
    main()
