"""등록된 부분 작업만 한 라운드 실행하고 최종판단으로 돌아갑니다."""

import asyncio
from collections.abc import Awaitable, Callable

from pydantic import ValidationError

from app.agents.decision import agent as decision
from app.schemas import (
    AgentAnalysis,
    AgentError,
    AnalysisTask,
    DecisionRequest,
    DecisionResult,
    SupplementEvent,
    SupplementPlan,
)

from .tools import SupplementTool

OnSupplement = Callable[[SupplementEvent], Awaitable[None]]


def validate_tools(tools: list[SupplementTool]) -> None:
    keys = [(tool.operation.agent_id, tool.operation.operation) for tool in tools]
    if len(keys) != len(set(keys)):
        raise ValueError("보완 작업이 중복 등록됐습니다.")
    for tool in tools:
        type(tool.operation).model_validate(tool.operation)
        if not callable(tool.execute) or not callable(tool.eligible):
            raise ValueError("보완 작업과 실행 가능 조건이 필요합니다.")
        if tool.accept is not None and not callable(tool.accept):
            raise ValueError("보완 자료의 채택 검증 함수가 필요합니다.")


async def decide_with_supplement(
    task: AnalysisTask,
    analyses: list[AgentAnalysis],
    *,
    tools: list[SupplementTool],
    generate: decision.GenerateDecision | None,
    on_event: OnSupplement | None,
    operation_timeout: float,
) -> DecisionResult:
    sources = {item.agent_id: item.model_copy(deep=True) for item in analyses}
    eligible = {
        (tool.operation.agent_id, tool.operation.operation): tool
        for tool in tools
        if tool.eligible(
            task.model_copy(deep=True), sources[tool.operation.agent_id].model_copy(deep=True)
        )
    }

    def request() -> DecisionRequest:
        return DecisionRequest(
            request_id=task.request_id,
            address=task.site.input_address,
            analyses=list(sources.values()),
        )

    outcome = await decision.evaluate(
        request(),
        generate=generate,
        operations=[tool.operation for tool in eligible.values()],
    )
    if isinstance(outcome, DecisionResult):
        return outcome

    feedback = []
    context: list[SupplementEvent] = []
    for asked in outcome.requests:

        async def emit(status, message, analysis=None, adopted=False, asked=asked):
            event = SupplementEvent(
                request_id=task.request_id,
                request=asked,
                status=status,
                message=message,
                analysis=analysis,
                adopted=adopted,
            )
            if on_event is not None:
                await on_event(event.model_copy(deep=True))
            if status != "requested":
                context.append(event)

        await emit("requested", "최종판단이 보완 작업을 요청했습니다.")
        tool = eligible.get((asked.agent_id, asked.operation))
        previous = sources[asked.agent_id]
        if tool is None or not tool.eligible(
            task.model_copy(deep=True), previous.model_copy(deep=True)
        ):
            message = f"보완 거절: {asked.agent_id} — 지원하지 않거나 실행 조건이 맞지 않습니다."
            await emit("rejected", message)
            feedback.append(message)
            continue
        try:
            async with asyncio.timeout(operation_timeout):
                produced = await tool.execute(
                    task.model_copy(deep=True), previous.model_copy(deep=True)
                )
        except ValidationError:
            await emit("failed", "보완 결과 계약 검증에 실패했습니다.")
            raise
        except Exception as exc:
            produced = AgentAnalysis(
                request_id=task.request_id,
                agent_id=asked.agent_id,
                status="error",
                error=AgentError(
                    code="SUPPLEMENT_TIMEOUT"
                    if isinstance(exc, TimeoutError)
                    else "SUPPLEMENT_FAILED",
                    message="보완 작업을 완료하지 못했습니다.",
                ),
            )
        try:
            candidate = AgentAnalysis.model_validate(produced)
            if candidate.request_id != task.request_id or candidate.agent_id != asked.agent_id:
                raise ValueError("보완 결과의 요청 ID 또는 에이전트 ID가 다릅니다.")
        except (ValidationError, ValueError):
            await emit("failed", "보완 결과 계약 검증에 실패했습니다.")
            raise
        # 부분 결과끼리는 자료가 더 나아졌는지 보장할 수 없어 자동 교체하지 않습니다.
        adopted = candidate.status == "ok" or (
            candidate.status == "partial" and previous.status in {"error", "no_data"}
        )
        if tool.accept is not None:
            # 실제 보완은 원본을 덮어쓰지 않고 검증된 추가 근거만 채택합니다.
            preserved = candidate.model_dump(exclude={"data"}) == previous.model_dump(
                exclude={"data"}
            ) and all(
                key in candidate.data and candidate.data[key] == value
                for key, value in previous.data.items()
            )
            adopted = (
                candidate.status in {"ok", "partial"}
                and preserved
                and tool.accept(previous.model_copy(deep=True), candidate.model_copy(deep=True))
            )
        message = (
            f"보완 완료: {asked.agent_id} — 갱신 결과를 사용합니다."
            if adopted
            else f"보완 미채택: {asked.agent_id} — 기존 결과를 유지합니다."
        )
        await emit(
            "failed" if candidate.status == "error" else "succeeded",
            message,
            candidate,
            adopted,
        )
        if adopted:
            sources[asked.agent_id] = candidate
        else:
            feedback.append(message)

    final = await decision.evaluate(
        request(), generate=generate, feedback=feedback, supplement_context=context
    )
    if isinstance(final, SupplementPlan):
        raise ValueError("보완 라운드를 추가 실행할 수 없습니다.")
    return final
