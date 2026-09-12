"""샘플 또는 실제 모델로 중재 에이전트를 실행합니다."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from app.agents.decision import analyze

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "decision"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="중재 에이전트 실행")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mock", action="store_true", help="기본 샘플 분석 입력과 실제 모델로 실행")
    mode.add_argument("--input", type=Path, help="분석 입력 파일과 실제 모델로 실행")
    parser.add_argument("--output", type=Path, help="결과를 저장할 새 파일")
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("결과 파일이 이미 있습니다. 새 경로를 지정해 주세요.")

    load_dotenv(ROOT / ".env", override=False)
    try:
        input_path = EXAMPLES / "input.json" if args.mock else args.input
        request = json.loads(input_path.read_text(encoding="utf-8-sig"))
        result = asyncio.run(analyze(request))
        output = result.model_dump_json(indent=2, exclude_none=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as file:
                file.write(output + "\n")
        else:
            print(output)
        return 0
    except ValidationError as exc:
        print("입출력 형식이 올바르지 않습니다.", file=sys.stderr)
        for error in exc.errors(include_input=False, include_url=False):
            print(f"{error['loc']}: {error['msg']}", file=sys.stderr)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"실행 실패: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
