import pandas as pd
from pathlib import Path


# ============================================================
# 기본 설정
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    BASE_DIR
    / "개롱역_2025Q2_70업종_매핑결과.csv"
)

OUTPUT_FILE = (
    BASE_DIR
    / "개롱역_2025Q2_70업종_점수결과.csv"
)


# ============================================================
# Lifecycle Score 가중치
# ============================================================

CLOSE_RATE_WEIGHT = 0.50
NET_CHANGE_WEIGHT = 0.30
TURNOVER_WEIGHT = 0.20


# ============================================================
# 1. 데이터 읽기
# ============================================================

df = pd.read_csv(
    INPUT_FILE,
    encoding="utf-8-sig"
)


print("전체 서비스 업종 수:", len(df))


# ============================================================
# 2. 점수 계산 가능한 업종만 선택
# ============================================================

score_mask = (
    (df["data_available"] == True)
    & df["store_count"].notna()
    & (df["store_count"] > 0)
    & df["close_rate"].notna()
    & df["net_change_rate"].notna()
    & df["turnover_rate"].notna()
)


score_df = df.loc[score_mask].copy()


print(
    "Lifecycle Score 계산 대상:",
    len(score_df)
)


# ============================================================
# 3. 폐업률 안정성 점수
#
# 폐업률 ↓ → 점수 ↑
# ============================================================

score_df["close_rate_score"] = (
    score_df["close_rate"]
    .rank(
        method="average",
        pct=True,
        ascending=False,
    )
    * 100
)


# ============================================================
# 4. 순증감률 점수
#
# (개업 - 폐업) / 점포수
#
# 높을수록 긍정적
# ============================================================

score_df["net_change_score"] = (
    score_df["net_change_rate"]
    .rank(
        method="average",
        pct=True,
        ascending=True,
    )
    * 100
)


# ============================================================
# 5. 회전 안정성 점수
#
# turnover_rate =
# 개업률 + 폐업률
#
# 낮을수록 안정적으로 판단
# ============================================================

score_df["turnover_score"] = (
    score_df["turnover_rate"]
    .rank(
        method="average",
        pct=True,
        ascending=False,
    )
    * 100
)


# ============================================================
# 6. Lifecycle Score
# ============================================================

score_df["lifecycle_score"] = (

    CLOSE_RATE_WEIGHT
    * score_df["close_rate_score"]

    + NET_CHANGE_WEIGHT
    * score_df["net_change_score"]

    + TURNOVER_WEIGHT
    * score_df["turnover_score"]
)


# 소수 첫째 자리
score_columns = [
    "close_rate_score",
    "net_change_score",
    "turnover_score",
    "lifecycle_score",
]

score_df[score_columns] = (
    score_df[score_columns].round(1)
)


# ============================================================
# 7. Confidence
#
# MVP 자체 기준
# ============================================================

def get_confidence(store_count):

    if pd.isna(store_count):
        return "none"

    if store_count >= 20:
        return "high"

    if store_count >= 5:
        return "medium"

    return "low"


score_df["confidence"] = (
    score_df["store_count"]
    .apply(get_confidence)
)


# ============================================================
# 8. 계산 결과를 70개 Master에 다시 결합
# ============================================================

score_result = score_df[
    [
        "service_id",
        "close_rate_score",
        "net_change_score",
        "turnover_score",
        "lifecycle_score",
        "confidence",
    ]
].copy()


final_df = df.merge(
    score_result,
    on="service_id",
    how="left",
)


# 데이터가 없는 업종
final_df["confidence"] = (
    final_df["confidence"].fillna("none")
)


# ============================================================
# 9. 컬럼 순서 정리
# ============================================================

final_df = final_df[
    [
        "service_id",
        "service_name",
        "data_available",

        # 실제 개폐업 데이터
        "store_count",
        "open_count",
        "close_count",
        "open_rate",
        "close_rate",
        "net_change",
        "net_change_rate",
        "turnover_rate",

        # 점수
        "close_rate_score",
        "net_change_score",
        "turnover_score",
        "lifecycle_score",

        # 신뢰도
        "confidence",

        # 매핑 정보
        "source_industry_count",
        "source_industries",

        # 데이터 누락 이유
        "missing_reason",
    ]
]


# ============================================================
# 10. CSV 저장
# ============================================================

final_df.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig",
)


# ============================================================
# 11. 검증
# ============================================================

print()
print("===== Lifecycle Score 결과 =====")

print(
    "점수 계산 업종 수:",
    final_df["lifecycle_score"].notna().sum()
)

print(
    "점수 없는 업종 수:",
    final_df["lifecycle_score"].isna().sum()
)


# ============================================================
# 상위 10개
# ============================================================

print()
print("===== Lifecycle Score 상위 10개 =====")

top10 = (
    final_df[
        final_df["lifecycle_score"].notna()
    ]
    .sort_values(
        "lifecycle_score",
        ascending=False
    )
    .head(10)
)


print(
    top10[
        [
            "service_id",
            "service_name",
            "store_count",
            "close_rate",
            "net_change_rate",
            "turnover_rate",
            "lifecycle_score",
            "confidence",
        ]
    ].to_string(index=False)
)


# ============================================================
# 하위 10개
# ============================================================

print()
print("===== Lifecycle Score 하위 10개 =====")

bottom10 = (
    final_df[
        final_df["lifecycle_score"].notna()
    ]
    .sort_values(
        "lifecycle_score",
        ascending=True
    )
    .head(10)
)


print(
    bottom10[
        [
            "service_id",
            "service_name",
            "store_count",
            "close_rate",
            "net_change_rate",
            "turnover_rate",
            "lifecycle_score",
            "confidence",
        ]
    ].to_string(index=False)
)


print()
print("저장 완료:")
print(OUTPUT_FILE)