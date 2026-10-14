"""공개 목업도 동일한 도구 루프·평가자·보고서 검증을 거칩니다."""

import json

from openai.types.chat import ChatCompletionMessage

from app.schemas import AGENT_IDS, AgentAnalysis, Scope, Site


def call(name, arguments):
    return ChatCompletionMessage(
        role="assistant",
        tool_calls=[
            {
                "id": "mock-call",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
            }
        ],
    )


def generators(*, ask=False):
    async def decision(messages, definitions, settings, receipt):
        receipt.update(model="mock", usage={"prompt_tokens": 0, "completion_tokens": 0})
        if ask and len(messages) == 2:
            return call(
                "ask_user",
                {
                    "questions": [
                        {"field": "floor", "question": "몇 층인가요?", "reason": "공간 조건 확인"}
                    ]
                },
            )
        final = any(m["role"] == "user" and '"reviews"' in m.get("content", "") for m in messages)
        return call(
            "submit_draft",
            {
                "phase": "final" if final else "draft",
                "report": {
                    "summary_segments": [{"type": "text", "text": "목업 자료로 검토한 결과입니다."}]
                },
            },
        )

    async def evaluator(messages, definitions, settings, receipt):
        receipt.update(model="mock", usage={"prompt_tokens": 0, "completion_tokens": 0})
        draft = json.loads(messages[1]["content"])["draft"]
        return call(
            "submit_review", {"draft_id": draft["report_id"], "verdict": "agree", "issues": []}
        )

    return {"generate": decision, "evaluator_generate": evaluator}


def dependencies(*, ask=False):
    async def resolve(address):
        return Site(input_address=address, road_address=address, latitude=37.552, longitude=126.925)

    def agent(name):
        async def analyze(task):
            return AgentAnalysis(
                request_id=task.request_id,
                agent_id=name,
                status="no_data",
                scope=Scope(area="목업", period="목업"),
            )

        return analyze

    return {
        "resolve": resolve,
        "agents": {name: agent(name) for name in AGENT_IDS},
        **generators(ask=ask),
    }
