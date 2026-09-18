"""개폐업 에이전트 전체 파이프라인을 단독 실행합니다."""

import argparse
import json
from pathlib import Path

from app.agents.business_lifecycle.agent import run_business_lifecycle_agent
from app.config import load_environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area-code", required=True, help="서울시 상권코드")
    parser.add_argument("--base-quarter", required=True, help="기준 분기. 예: 20252")
    parser.add_argument("--count", type=int, default=12, help="분석 분기 수")
    parser.add_argument("--request-id", help="외부 요청 ID")
    parser.add_argument("--output", type=Path, help="결과 JSON 저장 경로")
    args = parser.parse_args()

    load_environment()
    result = run_business_lifecycle_agent(
        area_code=args.area_code,
        base_quarter=args.base_quarter,
        quarter_count=args.count,
        request_id=args.request_id,
    )

    print("분석 업종:", len(result["industry_scores"]))
    print("판단 보류 업종:", len(result["unavailable_industries"]))
    print("요약:", result["summary"])
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Agent 결과 저장 완료:", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
