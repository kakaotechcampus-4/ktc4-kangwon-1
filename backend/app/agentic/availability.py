"""채점 가능 범위와 실제 관측·미적용·프로필 고정을 구분합니다."""

from app.agents.commercial_area.baseline import SEOUL_INDUSTRY_DENSITY_PERCENTILES
from app.industries.catalog import INDUSTRIES_WITHOUT_SEOUL


def classify_item(code: str, item: str, score: dict) -> str:
    status = score["status"]
    if status == "n.a.":
        return "not_applicable"
    if status == "observed":
        if item == "C1" and score.get("agglomeration") == "무관" and score.get("value") is None:
            return "profile_fixed"
        return "observed"
    if status != "unknown":
        raise ValueError("알 수 없는 채점 상태입니다.")
    if item == "L":
        return "unreviewed_llm"
    if item.startswith("S") and code in INDUSTRIES_WITHOUT_SEOUL:
        return "unsupported_source"
    if item == "C1" and SEOUL_INDUSTRY_DENSITY_PERCENTILES.get(code, {}).get(50, 0) < 0.01:
        return "sparse_baseline"
    reason = score.get("reason", "")
    if "부분 실패" in reason or "페이지 누락" in reason:
        return "partial_source"
    if "관측·전체 노출량 부족" in reason:
        # 기존 사유는 원천 불완전과 노출량 부족을 함께 나타냅니다.
        return "lifecycle_observation_shortage"
    if "노출량" in reason:
        return "insufficient_exposure"
    if "기간 불일치" in reason or "비중첩 비교창" in reason:
        return "period_unverified"
    if item == "C4":
        return "facility_unverified"
    return "unavailable_observation"


def coverage_notes(code: str, items: dict) -> list[str]:
    notes = []
    life = [items[name] for name in ("S1", "S2", "S3", "S4") if name in items]
    missing = [score for score in life if score["status"] == "unknown"]
    if missing:
        if code in INDUSTRIES_WITHOUT_SEOUL:
            notes.append("서울 개폐업 대응 업종이 없어 폐업·점포 변동 지표 평가 불가")
        elif len(life) == 4 and len(missing) == 4:
            notes.append("이 위치의 개폐업 지표 미확인: 관측량·분석 기간·원천 자료 확인 필요")
        else:
            notes.append("일부 개폐업 지표 미확인: 관측량·기간별 자료 확인 필요")
    c1 = items.get("C1")
    if c1 is not None:
        state = classify_item(code, "C1", c1)
        if state == "profile_fixed":
            notes.append("경쟁 점수에 업종 프로필의 중간 등급 적용: 현장 경쟁 관측값이 아님")
        elif state == "sparse_baseline":
            notes.append("같은 업종의 서울 밀도 기준선이 희소하여 경쟁 점수 미확인")
        elif c1["status"] == "unknown":
            notes.append("주변 경쟁 지표 미확인: 점포 집계·수요 자료 확인 필요")
    if items.get("C4", {}).get("status") == "unknown":
        notes.append("필요 시설의 거리 자료 미확인: 시설 부재로 판단하지 않음")
    age = items.get("D3", {})
    value = age.get("value")
    if (
        age.get("status") == "observed"
        and isinstance(value, dict)
        and value.get("requested_population") in {"상주", "직장"}
        and value.get("population") == "유동"
    ):
        notes.append("고객 연령 항목에 상주·직장 인구 대신 유동인구 대체 자료 사용")
    return notes
