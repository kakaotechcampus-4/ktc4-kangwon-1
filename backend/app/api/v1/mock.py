"""HTTP 연결 확인용 고정 시나리오입니다. 외부 API·모델을 호출하지 않습니다."""

import json
import uuid
from datetime import UTC, datetime

from app.industries.catalog import CATALOG_VERSION
from app.mocks import mock_generate
from app.schemas import MapData, MapObservation, MapQueryResult


def interactive_decision(*, with_map: bool, allow_questions: bool):
    def generate(prompt, payload):
        data = json.loads(payload)
        if with_map and data.get("map_observation") is None:
            return {
                "action": "map_lookup",
                "queries": [
                    {
                        "kind": "infrastructure",
                        "facility_code": "SW8",
                        "why_needed": "목업 교통 접근성 확인",
                        "expected_impact": "접근성 근거 보완",
                    }
                ],
            }
        if allow_questions and data.get("question_fields"):
            return {
                "action": "ask_user",
                "questions": [
                    {
                        "field": "floor",
                        "text": "공실은 몇 층인가요?",
                        "why_needed": "목업 보행 접근성 확인",
                        "expected_impact": "접근 조건 확인",
                    }
                ],
            }
        return mock_generate(prompt, payload)

    return generate


async def map_observation(task, plan):
    return MapObservation(
        request_id=task.request_id,
        observation_id=uuid.uuid4().hex,
        site=task.site,
        radius_m=task.radius_m,
        queried_at=datetime.now(UTC).isoformat(),
        master_version=CATALOG_VERSION,
        status="no_data",
        warnings=["외부 조회 없는 목업입니다."],
        data=MapData(
            queries={
                f"q{i}": MapQueryResult(
                    request=q,
                    status="ok",
                    method="category" if q.facility_code else "keyword",
                    category_code=q.facility_code,
                    total_count=0,
                    has_more=False,
                )
                for i, q in enumerate(plan.unique_queries(), 1)
            }
        ),
    )
