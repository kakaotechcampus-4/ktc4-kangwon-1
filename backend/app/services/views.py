"""저장 자료를 기존 GET 상세 응답 형태로 조립합니다."""

import asyncio
from dataclasses import asdict

from app.db.analysis_repository import SqliteAnalysisRepository
from app.storage.contracts import AnalysisRepositoryProtocol
from app.storage.models import StoredAnalysisDetail


async def analysis_detail(request_id: str, db_path):
    return await _analysis_detail(request_id, SqliteAnalysisRepository(db_path))


async def _analysis_detail(request_id: str, storage: AnalysisRepositoryProtocol):
    data = await asyncio.to_thread(storage.get_detail, request_id)
    if data is not None:
        return _detail_response(data)


def _detail_response(data: StoredAnalysisDetail) -> dict:
    row = asdict(data.request)
    execution = data.execution
    if execution.get("capabilities", {}).get("evaluators"):
        saved = data.evaluation
        row["evaluation"] = {
            "skipped": execution.get("evaluation_skipped"),
            "draft": {k: v for k, v in saved.draft.items() if k != "request_id"} if saved else None,
            "evaluations": [
                e.model_dump(mode="json", exclude={"notes", "request_id"})
                for e in saved.evaluations
            ]
            if saved
            else [],
            "log": [e.model_dump(mode="json") for e in saved.log] if saved else [],
        }
    if row["analysis_mode"] == "multi_agent":
        state = data.deliberation
        if state is None:
            raise ValueError("저장된 전문가 실행 자료가 없습니다.")
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
    row.update(site=data.site, result=data.result, error=data.error)
    row.update(_details(data))
    return row


def _details(data: StoredAnalysisDetail):
    return {
        "decision_failures": data.decision_failures,
        "questions": data.questions.model_dump(mode="json") if data.questions else None,
        "analyses": [{"attempt": r.attempt, "analysis": r.analysis} for r in data.analyses],
        "supplements": data.supplements,
        "map_status": data.map_status,
        "map_observation": data.map_observation,
    }
