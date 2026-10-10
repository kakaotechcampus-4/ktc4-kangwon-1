"""기존 SQLite 업무 트랜잭션을 저장소 계약에 연결합니다."""

import json
from pathlib import Path

from app.schemas import (
    AgentAnalysis,
    AgentBrief,
    AnalysisTask,
    AnswerSubmission,
    DecisionResult,
    Evaluation,
    EvaluationLogEntry,
    MapLookupPlan,
    MapObservation,
    SpecialistAnswer,
    SupplementEvent,
)
from app.storage.models import (
    ResumeBundle,
    StoredAnalysisAttempt,
    StoredAnalysisDetail,
    StoredEvaluation,
    StoredRequest,
)

from . import repository


class SqliteAnalysisRepository:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path

    def claim_answers(self, submission: AnswerSubmission) -> bool:
        return repository.claim_question_resume(submission, db_path=self.db_path)

    def load_resume(self, request_id: str) -> ResumeBundle:
        return repository.load_resume_context(request_id, db_path=self.db_path)

    def claim_retry(self, request_id: str, failed_at: str) -> ResumeBundle:
        return repository.claim_decision_retry(request_id, failed_at, db_path=self.db_path)

    def complete(
        self, result: DecisionResult, *, attempt: int, source_attempts: dict[str, int]
    ) -> None:
        repository.complete_request(
            result, attempt=attempt, source_attempts=source_attempts, db_path=self.db_path
        )

    def get_detail(self, request_id: str) -> StoredAnalysisDetail | None:
        data = repository.get_analysis_view_data(request_id, db_path=self.db_path)
        if data is None:
            return None
        row = data["request"]
        snapshot, mapped, evaluation = data["questions"], data["map"], data["evaluation"]
        return StoredAnalysisDetail(
            request=StoredRequest(
                request_id=row["request_id"],
                input_address=row["input_address"],
                catalog_version=row["catalog_version"],
                analysis_mode=row["analysis_mode"],
                radius_m=row["radius_m"],
                status=row["status"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            ),
            execution=json.loads(row["execution_json"]),
            site=json.loads(row["site_json"]) if row["site_json"] is not None else None,
            result=json.loads(row["result_json"]) if row["result_json"] is not None else None,
            error=json.loads(row["error_json"]) if row["error_json"] is not None else None,
            analyses=[
                StoredAnalysisAttempt(attempt=r["attempt"], analysis=json.loads(r["analysis_json"]))
                for r in data["analyses"]
            ],
            supplements=[json.loads(r["event_json"]) for r in data["supplements"]],
            questions=snapshot.waiting if snapshot else None,
            map_status=mapped["status"] if mapped else None,
            map_observation=mapped["observation"] if mapped else None,
            evaluation=StoredEvaluation(**evaluation) if evaluation else None,
            deliberation=data["deliberation"],
            decision_failures=data["decision_failures"],
        )

    def save_site(self, task: AnalysisTask) -> None:
        return repository.save_site(task, db_path=self.db_path)

    def save_agent(self, analysis: AgentAnalysis) -> None:
        return repository.save_agent(analysis, db_path=self.db_path)

    def start_map_lookup(self, task: AnalysisTask, plan: MapLookupPlan) -> int:
        return repository.start_map_lookup(task, plan, db_path=self.db_path)

    def complete_map_lookup(self, observation: MapObservation, *, adopted: bool = True) -> None:
        return repository.complete_map_lookup(observation, adopted=adopted, db_path=self.db_path)

    def save_supplement_event(self, event: SupplementEvent) -> int | None:
        return repository.save_supplement_event(event, db_path=self.db_path)

    def save_agent_brief(self, brief: AgentBrief) -> None:
        return repository.save_agent_brief(brief, db_path=self.db_path)

    def save_specialist_answer(self, answer: SpecialistAnswer) -> None:
        return repository.save_specialist_answer(answer, db_path=self.db_path)

    def save_evaluation(self, draft: DecisionResult, evaluations: list[Evaluation]) -> None:
        return repository.save_evaluation(draft, evaluations, db_path=self.db_path)

    def save_evaluation_log(self, request_id: str, entries: list[EvaluationLogEntry]) -> None:
        return repository.save_evaluation_log(request_id, entries, db_path=self.db_path)

    def update_execution_state(self, request_id: str, *, evaluation_skipped: str) -> None:
        return repository.update_execution_state(
            request_id, evaluation_skipped=evaluation_skipped, db_path=self.db_path
        )
