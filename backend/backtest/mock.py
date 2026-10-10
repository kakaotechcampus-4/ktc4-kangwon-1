import json

from backtest.outcome import MIN_STORES

MOCK_MODEL = "backtest_mock"


def _store_counts(payload: dict) -> dict[str, float]:
    for analysis in payload.get("analyses", []):
        if analysis.get("agent_id") == "commercial_area":
            rows = (analysis.get("data") or {}).get("by_middle") or []
            return {f"/by_middle/{i}/count": row.get("count") or 0 for i, row in enumerate(rows)}
    return {}


def backtest_generate(system_prompt: str, input_json: str) -> dict:
    payload = json.loads(input_json)
    counts = _store_counts(payload)
    counted = []
    for entry in payload.get("industry_evidence", []):
        if entry["agent_id"] != "commercial_area":
            continue
        path = next(
            (p for p in entry["paths"] if p.startswith("/by_middle/") and p.endswith("/count")),
            None,
        )
        if path:
            counted.append((entry["industry_code"], path))
    if len(counted) < 2:
        return {
            "status": "no_data",
            "summary": "비교할 업종 자료가 부족합니다.",
            "recommendations": [],
            "not_recommended": [],
            "limitations": ["대역 판정: 상권 점포 자료 부족"],
        }
    best = counted[0]
    present = [c for c in counted[1:] if counts.get(c[1], 0) >= MIN_STORES]
    worst = present[-1] if present else counted[-1]

    def item(code, path, score):
        return {
            "category": {"code": code},
            "score": score,
            "reasons": ["반경 안 점포가 {0}개입니다."],
            "evidence": [{"agent_id": "commercial_area", "path": path}],
            "risks": [],
        }

    return {
        "status": "ok",
        "summary": "대역 판정입니다.",
        "recommendations": [item(*best, 70)],
        "not_recommended": [item(*worst, 30)],
        "limitations": ["백테스트 대역 판정 결과입니다."],
    }
