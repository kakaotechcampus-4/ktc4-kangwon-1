"""단독 실행 — 위경도로 바로 돌려본다.

    uv run python -m app.agents.floating_population
        37.5183291 127.1051123 "서울특별시 송파구 오금로 404"

오케스트레이터가 붙기 전까지 수동 확인용이다. status 가 error 면 종료코드 1.
"""

from __future__ import annotations

import sys
import uuid

from app.schemas import AnalysisTask, Site

from .agent import analyze

USAGE = (
    '사용법: python -m app.agents.floating_population <위도> <경도> "<주소>"\n'
    "  예:   python -m app.agents.floating_population "
    '37.5183291 127.1051123 "서울특별시 송파구 오금로 404"'
)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    if len(sys.argv) < 4:
        print(USAGE, file=sys.stderr)
        return 2

    try:
        latitude = float(sys.argv[1])
        longitude = float(sys.argv[2])
    except ValueError:
        print("위도·경도는 숫자여야 합니다.", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2

    address = " ".join(sys.argv[3:])
    task = AnalysisTask(
        request_id=str(uuid.uuid4()),
        site=Site(
            input_address=address,
            road_address=address,
            latitude=latitude,
            longitude=longitude,
        ),
    )

    analysis = analyze(task)
    print(analysis.model_dump_json(indent=2))
    if analysis.status == "error" and analysis.error is not None:
        print(f"[error] {analysis.error.code}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
