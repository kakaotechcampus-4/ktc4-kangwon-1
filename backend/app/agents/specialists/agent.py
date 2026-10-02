"""도메인별 계산을 재사용하며 제한 횟수만 도구를 선택하는 전문가입니다."""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from importlib.resources import files

from openai.types.chat import ChatCompletionMessage
from pydantic import Field, ValidationError

from app.evidence import (
    FINDING_WARNING_PREFIX,
    MAP_AGENT_ID,
    SourceIndex,
    validate_findings,
)
from app.industries.lookup import industry_terms
from app.llm.budget import BudgetStorageError, current_scope, llm_scope
from app.llm.client import complete_tools
from app.llm.config import LLMSettings
from app.logging import log_exception
from app.schemas import (
    AgentAnalysis,
    AgentBrief,
    AnalysisTask,
    Finding,
    MapObservation,
    Schema,
    SpecialistAnswer,
    SpecialistQuery,
    Text,
    ToolCallRecord,
)

from .facts import BRIEF_CONTEXT_KEYS, build_facts
from .map_inputs import query_summary, selected_citations
from .tools import ToolArgumentError, fallback_brief

logger = logging.getLogger(__name__)


GenerateSpecialist = Callable[[list, list], Awaitable[dict | ChatCompletionMessage]]


class BriefContent(Schema):
    headline: str = Field(min_length=1, max_length=200)
    findings: list[Finding] = Field(max_length=8)
    limitations: list[Text] = Field(default_factory=list)


async def generate_specialist(messages, definitions, *, settings: LLMSettings):
    return await complete_tools(messages, definitions, settings)


async def _run(agent_id, payload, *, generate, tools, get_data, get_observation=None, max_steps=5):
    prompt = await asyncio.to_thread(
        files(__package__).joinpath("prompt.md").read_text, encoding="utf-8"
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    finish = {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "확인한 근거로 브리핑 또는 답변을 제출합니다.",
            "parameters": BriefContent.model_json_schema(),
        },
    }
    records = []
    with llm_scope(current_scope()[0], agent_id):
        for step in range(max_steps):
            # 마지막 차례에는 finish만 제공해 도구를 쓴 뒤에도 답변을 정리하게 합니다.
            last = step == max_steps - 1 or len(records) >= 4
            definitions = [finish, *([] if last else [t.definition for t in tools.values()])]
            try:
                produced = await generate(messages, definitions)
                message = ChatCompletionMessage.model_validate(produced)
                if not message.tool_calls or len(message.tool_calls) != 1:
                    raise ValueError("도구는 한 번에 하나만 선택합니다.")
                call = message.tool_calls[0]
                if call.type != "function":
                    raise ValueError("지원하지 않는 도구 종류입니다.")
                name = call.function.name
                arguments = json.loads(call.function.arguments)
                if not isinstance(arguments, dict):
                    raise ValueError("도구 인자는 객체여야 합니다.")
                if name == "finish":
                    # 형식이 틀린 주장 하나 때문에 브리핑 전체를 버리지 않고 그 주장만 제외합니다.
                    raw = arguments.get("findings")
                    kept, dropped = [], []
                    for i, item in enumerate(raw if isinstance(raw, list) else []):
                        try:
                            kept.append(Finding.model_validate(item))
                        except ValidationError:
                            dropped.append(f"{FINDING_WARNING_PREFIX}: {i + 1}번 형식 오류")
                    content = BriefContent.model_validate({**arguments, "findings": kept[:8]})
                    content.limitations.extend(dropped)
                    observation = get_observation() if get_observation else None
                    findings, warnings = validate_findings(
                        content.findings,
                        agent_id=agent_id,
                        data=observation.data
                        if agent_id == MAP_AGENT_ID and observation
                        else get_data(),
                        radii={observation.radius_m}
                        if agent_id == MAP_AGENT_ID and observation
                        else None,
                    )
                    content.findings = findings
                    content.limitations.extend(warnings)
                    return content, records
            except (BudgetStorageError, OSError, asyncio.CancelledError):
                raise
            except Exception as exc:
                log_exception(logger, "전문가 모델 응답 실패", exc)
                return None, records
            if last:
                break
            started = time.monotonic()
            if name not in tools:
                result = {"error": "등록되지 않은 도구입니다."}
                status = "rejected"
            else:
                # 저장·취소·원자료 계약 오류는 대체 브리핑으로 숨기지 않습니다.
                try:
                    result = await tools[name].execute(arguments)
                    status = "error" if "error" in result else "ok"
                except ToolArgumentError:
                    result, status = {"error": "도구 인자가 올바르지 않습니다."}, "rejected"
            records.append(
                ToolCallRecord(
                    tool=name,
                    arguments=arguments,
                    status=status,
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
            )
            messages.extend(
                [
                    message.model_dump(mode="json", exclude_none=True),
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    },
                ]
            )
    return None, records


async def write_brief(
    task: AnalysisTask, analysis: AgentAnalysis, *, generate, tools, get_data=None, max_steps=5
) -> AgentBrief:
    content, records = await _run(
        analysis.agent_id,
        {
            "agent_id": analysis.agent_id,
            "task": "브리핑",
            "source": {
                "status": analysis.status,
                "scope": analysis.scope.model_dump(mode="json") if analysis.scope else None,
                "warnings": analysis.warnings,
                **{
                    key: value
                    for key, value in analysis.data.items()
                    if key in BRIEF_CONTEXT_KEYS and isinstance(value, str)
                },
            },
            "facts": build_facts(SourceIndex.build(analysis.data)),
        },
        generate=generate,
        tools=tools,
        get_data=get_data or (lambda: analysis.data),
        max_steps=max_steps,
    )
    if content is None or not content.findings:
        fallback = fallback_brief(
            task, analysis.model_copy(update={"data": get_data()}) if get_data else analysis
        )
        fallback.tool_calls = records
        return fallback
    return AgentBrief(
        request_id=task.request_id,
        agent_id=analysis.agent_id,
        source="model",
        **content.model_dump(),
        tool_calls=records,
    )


async def answer_query(
    task: AnalysisTask,
    query: SpecialistQuery,
    round_number: int,
    *,
    analysis: AgentAnalysis | None,
    observation: MapObservation | None,
    generate,
    tools,
    get_data=None,
    get_observation=None,
    max_steps=5,
) -> SpecialistAnswer:
    data = (
        observation.data.model_dump(mode="json")
        if query.agent_id == MAP_AGENT_ID and observation
        else analysis.data
        if analysis
        else {}
    )
    content, records = await _run(
        query.agent_id,
        {
            "agent_id": query.agent_id,
            "question": query.model_dump(mode="json"),
            **(
                {
                    "citations": selected_citations(
                        observation.data if observation else data,
                        {*query.industry_codes, "_facility"},
                    ),
                    "queries": {
                        key: query_summary(value) for key, value in observation.data.queries.items()
                    }
                    if observation
                    else {},
                    "industry_terms": {code: industry_terms(code) for code in query.industry_codes},
                }
                if query.agent_id == MAP_AGENT_ID
                else {
                    "facts": build_facts(SourceIndex.build(data), codes=set(query.industry_codes))
                }
            ),
        },
        generate=generate,
        tools=tools,
        get_data=get_data or (lambda: data),
        get_observation=get_observation or (lambda: observation),
        max_steps=max_steps,
    )
    findings = content.findings[:5] if content else []
    limitations = content.limitations if content else ["전문가 답변을 완료하지 못했습니다."]
    return SpecialistAnswer(
        request_id=task.request_id,
        round=round_number,
        query=query,
        status="partial" if findings and limitations else "answered" if findings else "unavailable",
        findings=findings,
        limitations=limitations,
        tool_calls=records,
    )
