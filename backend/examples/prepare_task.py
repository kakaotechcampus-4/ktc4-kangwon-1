"""주소 준비만 실행합니다. 좌표는 가상 값이며 실제 분석에 사용할 수 없습니다.

백엔드 설치 후 실행: python examples/prepare_task.py --mock
카카오 연결 시 같은 주소 → Site 계약의 비동기 함수를 전달하면 됩니다.
"""

import argparse
import asyncio
import sys

from app.agents.orchestration import prepare_task
from app.schemas import Site

MOCK_ADDRESS = "서울특별시 송파구 오금로 404 원일빌딩 1층, 올리브영 개롱역점"


async def mock_resolve(address: str) -> Site:
    """지정된 예시 주소만 처리하며 외부 서비스를 호출하지 않습니다."""
    if address != MOCK_ADDRESS:
        raise ValueError("지원하지 않는 목업 주소입니다. --address를 생략해 주세요.")
    return Site(
        input_address=address,
        road_address="서울특별시 송파구 오금로 404",
        detail_address="원일빌딩 1층, 올리브영 개롱역점",
        # 테스트용 가상 좌표이며 개롱역의 실제 위치가 아닙니다.
        latitude=0.0,
        longitude=0.0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", required=True, help="외부 연결 없이 실행")
    parser.add_argument("--address", default=MOCK_ADDRESS, help="지정된 목업 주소")
    args = parser.parse_args()
    print("목업 실행: 좌표는 가상 값입니다. 실제 분석에 사용하지 마세요.", file=sys.stderr)
    try:
        task = asyncio.run(prepare_task(args.address, resolve=mock_resolve))
    except ValueError as exc:
        print(f"실행 실패: {exc}", file=sys.stderr)
        return 1
    print(task.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
