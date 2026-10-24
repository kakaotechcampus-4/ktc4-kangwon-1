"""C1 fact가 어느 업종 집적 유형의 값인지 알리는 단위 문구입니다."""

NEARBY_UNIT = "배수(근처형: 유동 보정 밀도, 낮을수록 유리)"
CLUSTER_UNIT = "배수(모임형: 서울 중앙 밀도 대비, 높을수록 유리·상위 5% 초과 감점)"
PROFILE_UNIT = "업종 집적 유형(프로필)"

C1_UNITS = {"근처형": NEARBY_UNIT, "모임형": CLUSTER_UNIT, "무관": PROFILE_UNIT}


def c1_unit(score):
    kind = score.get("agglomeration")
    if kind not in C1_UNITS:
        raise ValueError(f"C1 점수에 집적 유형이 없습니다: {kind!r}")
    return C1_UNITS[kind]
