"""저장 자료를 기존 GET 상세 응답 형태로 조립합니다."""

import asyncio
import json

from app.db import repository


async def analysis_detail(request_id: str, db_path):
    data = await asyncio.to_thread(repository.get_analysis_view_data, request_id, db_path=db_path)
    if data is not None:
        row = data["request"]
        execution = json.loads(row.pop("execution_json", "{}"))
        if execution.get("capabilities", {}).get("evaluators"):
            saved = data["evaluation"]
            row["evaluation"] = {
                "skipped": execution.get("evaluation_skipped"),
                "draft": {k: v for k, v in saved["draft"].items() if k != "request_id"}
                if saved
                else None,
                "evaluations": [
                    e.model_dump(mode="json", exclude={"notes", "request_id"})
                    for e in saved["evaluations"]
                ]
                if saved
                else [],
                "log": [e.model_dump(mode="json") for e in saved["log"]] if saved else [],
            }
        if row["analysis_mode"] == "multi_agent":
            state = data["deliberation"]
            row["deliberation"] = {
                "briefs": [b.model_dump(mode="json") for b in state["briefs"]],
                "answers": [
                    a.model_dump(mode="json", exclude={"analysis", "map_observation"})
                    for a in state["specialist_answers"]
                ],
                "consult_round": state["consult_round"],
                "map_attempt": state["map_attempt"],
                "budget": state["execution"].get("budget", {"used": 0, "calls": []}),
                "elapsed_seconds": state["execution"].get("elapsed_seconds", 0),
            }
        # 과거 업종명·스키마는 저장 당시 값 그대로 반환합니다.
        for name in ("site", "result", "error"):
            value = row.pop(f"{name}_json")
            row[name] = json.loads(value) if value is not None else None
        row.update(_details(data))
        return row


def _details(data):
    snapshot = data["questions"]
    mapped = data["map"]
    return {
        "decision_failures": data["decision_failures"],
        "questions": snapshot.waiting.model_dump(mode="json") if snapshot else None,
        "analyses": [
            {"attempt": r["attempt"], "analysis": json.loads(r["analysis_json"])}
            for r in data["analyses"]
        ],
        "supplements": [json.loads(r["event_json"]) for r in data["supplements"]],
        "map_status": mapped["status"] if mapped else None,
        "map_observation": mapped["observation"] if mapped else None,
    }
