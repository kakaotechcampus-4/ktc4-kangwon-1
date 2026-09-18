"""입력은 목업, 모델은 실제 엘리스 API로 실행합니다.

실제 모델: python examples/run_orchestration.py --mock
전체 대역: python examples/run_orchestration.py --mock --offline
좌표와 분석 자료는 가상 값입니다. 카카오 및 상권 데이터 API는 호출하지 않습니다.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from openai.types.chat import ChatCompletionMessage
from prepare_task import MOCK_ADDRESS, mock_resolve

from app.config import load_environment
from app.schemas import DecisionRequest
from app.services.analysis import execute_analysis
from app.services.settings import ExecutionSettings

DECISION_FOLDER = Path(__file__).resolve().parent / "decision"


async def run(offline: bool, *, db_path: str | Path | None = None):
    """기존 개롱역 분석 목업을 연결하고 요청 ID만 현재 요청에 맞춥니다."""
    folder = DECISION_FOLDER
    input_json = await asyncio.to_thread((folder / "input.json").read_text, encoding="utf-8")
    source = DecisionRequest.model_validate_json(input_json)
    if source.address != MOCK_ADDRESS:
        raise ValueError("주소 목업과 분석 목업의 위치가 다릅니다.")

    def make_agent(analysis):
        async def analyze(task):
            return analysis.model_copy(update={"request_id": task.request_id}, deep=True)

        return analyze

    actions = iter(("prepare_address", "run_analyses", "make_decision"))

    async def mock_action(messages, definitions):
        name = next(actions)
        return ChatCompletionMessage.model_validate(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": f"call-{name}",
                        "type": "function",
                        "function": {"name": name, "arguments": "{}"},
                    }
                ],
            }
        )

    def mock_decision(system_prompt, input_json):
        return json.loads((folder / "response.json").read_text("utf-8"))

    return await execute_analysis(
        source.address,
        resolve=mock_resolve,
        agents={item.agent_id: make_agent(item) for item in source.analyses},
        generate_action=mock_action if offline else None,
        generate=mock_decision if offline else None,
        db_path=db_path,
        settings=ExecutionSettings() if offline else ExecutionSettings.from_env(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", required=True, help="가상 입력 사용")
    parser.add_argument("--offline", action="store_true", help="LLM도 대역으로 실행")
    parser.add_argument("--db", type=Path, help="결과를 저장할 SQLite 파일")
    args = parser.parse_args()
    if not args.offline:
        load_environment()
    print("목업 자료·가상 좌표입니다. 실제 상권 판단에 사용하지 마세요.", file=sys.stderr)
    try:
        result = asyncio.run(run(args.offline, db_path=args.db))
    except (ValueError, RuntimeError) as exc:
        print(f"실행 실패: {exc}", file=sys.stderr)
        return 1
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
