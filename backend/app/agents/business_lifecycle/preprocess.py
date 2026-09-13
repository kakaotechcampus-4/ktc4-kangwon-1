from pathlib import Path

import pandas as pd
from mapping import (
    EXCLUDED_SEOUL_INDUSTRIES,
    SEOUL_TO_SERVICE,
    SERVICE_INDUSTRIES,
    UNSUPPORTED_SERVICE_INDUSTRIES,
)

# ============================================================
# 기본 설정
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = BASE_DIR / "서울시 상권분석서비스(점포-상권)_2025년.csv"

RAW_OUTPUT_FILE = BASE_DIR / "개롱역_2025Q2_원본추출.csv"
MAPPED_OUTPUT_FILE = BASE_DIR / "개롱역_2025Q2_70업종_매핑결과.csv"

TARGET_AREA_CODE = 3120240
TARGET_AREA_NAME = "개롱역"
TARGET_QUARTER = 20252


# ============================================================
# 1. 원본 CSV 읽기
# ============================================================

df = pd.read_csv(
    INPUT_FILE,
    encoding="cp949",
    dtype={"svc_induty_cd": str},
)

print("전체 데이터 행 수:", len(df))


# ============================================================
# 2. 개롱역 + 2025년 2분기 추출
# ============================================================

target_df = df[
    (df["trdar_cd"] == TARGET_AREA_CODE)
    & (df["stdr_yyqu_cd"] == TARGET_QUARTER)
].copy()


print()
print("===== 원본 추출 결과 =====")
print("상권:", TARGET_AREA_NAME)
print("상권 코드:", TARGET_AREA_CODE)
print("기준 분기:", TARGET_QUARTER)
print("원본 업종 행 수:", len(target_df))
print("고유 서울시 업종 수:", target_df["svc_induty_cd"].nunique())


# ============================================================
# 3. 필요한 컬럼만 선택
# ============================================================

target_df = target_df[
    [
        "stdr_yyqu_cd",
        "trdar_cd",
        "trdar_cd_nm",
        "svc_induty_cd",
        "svc_induty_cd_nm",
        "stor_co",
        "similr_induty_stor_co",
        "opbiz_rt",
        "opbiz_stor_co",
        "clsbiz_rt",
        "clsbiz_stor_co",
        "frc_stor_co",
    ]
].copy()


# 원본 추출 결과 저장
target_df.to_csv(
    RAW_OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig",
)


# ============================================================
# 4. 서울시 업종 → 우리 서비스 업종 매핑
# ============================================================

target_df["service_id"] = target_df["svc_induty_cd"].map(
    SEOUL_TO_SERVICE
)

target_df["service_name"] = target_df["service_id"].map(
    SERVICE_INDUSTRIES
)


# ============================================================
# 5. 매핑 상태 확인
# ============================================================

mapped_df = target_df[
    target_df["service_id"].notna()
].copy()


excluded_df = target_df[
    target_df["svc_induty_cd"].isin(
        EXCLUDED_SEOUL_INDUSTRIES.keys()
    )
].copy()


unknown_df = target_df[
    target_df["service_id"].isna()
    & ~target_df["svc_induty_cd"].isin(
        EXCLUDED_SEOUL_INDUSTRIES.keys()
    )
].copy()


print()
print("===== 매핑 확인 =====")
print("매핑된 서울시 원본 행:", len(mapped_df))
print("의도적으로 제외된 행:", len(excluded_df))
print("매핑되지 않은 미확인 행:", len(unknown_df))


if len(excluded_df) > 0:
    print()
    print("[의도적으로 제외된 서울시 업종]")

    for _, row in excluded_df.iterrows():
        print(
            row["svc_induty_cd"],
            row["svc_induty_cd_nm"],
        )


if len(unknown_df) > 0:
    print()
    print("[주의: mapping.py에 없는 서울시 업종]")

    for _, row in unknown_df.iterrows():
        print(
            row["svc_induty_cd"],
            row["svc_induty_cd_nm"],
        )


# ============================================================
# 6. 같은 서비스 업종끼리 합산
# ============================================================

aggregated_df = (
    mapped_df
    .groupby(
        ["service_id", "service_name"],
        as_index=False
    )
    .agg(
        # 전체 점포수
        store_count=("similr_induty_stor_co", "sum"),

        # 2025 Q2 개업 / 폐업 수
        open_count=("opbiz_stor_co", "sum"),
        close_count=("clsbiz_stor_co", "sum"),

        # 몇 개의 서울시 업종이 합쳐졌는지
        source_industry_count=("svc_induty_cd", "nunique"),

        # 실제 합쳐진 원업종
        source_industries=(
            "svc_induty_cd_nm",
            lambda x: " | ".join(sorted(set(x)))
        ),
    )
)


aggregated_df["service_id"] = (
    aggregated_df["service_id"].astype(int)
)


# ============================================================
# 7. 통합 후 개폐업 지표 다시 계산
#
# 서울시 원본의 개업률 / 폐업률을 평균하지 않고
# 통합된 점포수와 개폐업수로 새로 계산
# ============================================================

aggregated_df["open_rate"] = (
    aggregated_df["open_count"]
    / aggregated_df["store_count"]
    * 100
)

aggregated_df["close_rate"] = (
    aggregated_df["close_count"]
    / aggregated_df["store_count"]
    * 100
)


aggregated_df["net_change"] = (
    aggregated_df["open_count"]
    - aggregated_df["close_count"]
)


aggregated_df["net_change_rate"] = (
    aggregated_df["net_change"]
    / aggregated_df["store_count"]
    * 100
)


aggregated_df["turnover_rate"] = (
    aggregated_df["open_rate"]
    + aggregated_df["close_rate"]
)


rate_columns = [
    "open_rate",
    "close_rate",
    "net_change_rate",
    "turnover_rate",
]

aggregated_df[rate_columns] = (
    aggregated_df[rate_columns].round(2)
)


# ============================================================
# 8. 우리 서비스 70개 Master 생성
# ============================================================

master_df = pd.DataFrame(
    [
        {
            "service_id": service_id,
            "service_name": service_name,
        }
        for service_id, service_name
        in SERVICE_INDUSTRIES.items()
    ]
)


# ============================================================
# 9. 실제 데이터 LEFT JOIN
# ============================================================

final_df = master_df.merge(
    aggregated_df,
    on=["service_id", "service_name"],
    how="left",
)


# ============================================================
# 10. 데이터 존재 여부
# ============================================================

final_df["data_available"] = (
    final_df["store_count"].notna()
)


# ============================================================
# 11. 누락 이유
# ============================================================

def get_missing_reason(row):

    if row["data_available"]:
        return None

    service_id = row["service_id"]

    if service_id in UNSUPPORTED_SERVICE_INDUSTRIES:
        return "서울시 생활밀접업종 데이터에 직접 대응 업종 없음"

    return "개롱역 2025Q2에 대응 서울시 업종 데이터 없음"


final_df["missing_reason"] = final_df.apply(
    get_missing_reason,
    axis=1,
)


# ============================================================
# 12. 컬럼 순서
# ============================================================

final_df = final_df[
    [
        "service_id",
        "service_name",
        "data_available",

        "store_count",
        "open_count",
        "close_count",

        "open_rate",
        "close_rate",

        "net_change",
        "net_change_rate",

        "turnover_rate",

        "source_industry_count",
        "source_industries",

        "missing_reason",
    ]
]


# ============================================================
# 13. 저장
# ============================================================

final_df.to_csv(
    MAPPED_OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig",
)


# ============================================================
# 14. 검증
# ============================================================

available_count = int(
    final_df["data_available"].sum()
)

missing_count = (
    len(final_df) - available_count
)


print()
print("===== 우리 서비스 70개 변환 결과 =====")
print("전체 서비스 업종 수:", len(final_df))
print("데이터 존재 업종 수:", available_count)
print("데이터 없는 업종 수:", missing_count)


print()
print(
    "통합 후 총 점포수:",
    int(final_df["store_count"].fillna(0).sum())
)

print(
    "통합 후 총 개업수:",
    int(final_df["open_count"].fillna(0).sum())
)

print(
    "통합 후 총 폐업수:",
    int(final_df["close_count"].fillna(0).sum())
)


print()
print("저장 완료:")
print(MAPPED_OUTPUT_FILE)