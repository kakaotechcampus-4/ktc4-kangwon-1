"""골든 요약을 실제 모델로 다시 받아 채점합니다."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from app.agents.commercial_area.config import Settings, load_dotenv_if_present
from app.agents.commercial_area.llm import render_summary_text, summarize
from app.agents.commercial_area.scoring import check, errors

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "tests" / "data" / "commercial_area_eval"


async def run() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--only")
    args = parser.parse_args()

    load_dotenv_if_present()
    overrides = {"llm_model": args.model} if args.model else {}
    settings = Settings.from_env(**overrides)
    if not settings.llm_model:
        print("ELICE_MODEL 이 없어 모델을 부를 수 없습니다.", file=sys.stderr)
        return 1

    paths = sorted(GOLDEN_DIR.glob("*.json"))
    if args.only:
        paths = [p for p in paths if p.stem == args.only]
        if not paths:
            stems = ", ".join(sorted(p.stem for p in GOLDEN_DIR.glob("*.json")))
            print(f"'{args.only}' 골든이 없습니다. 고를 수 있는 것: {stems}", file=sys.stderr)
            return 1
    if not paths:
        print("갱신할 골든이 없습니다.", file=sys.stderr)
        return 1

    print(f"모델: {settings.llm_model}")
    failed = 0
    ready: list[tuple[Path, dict[str, Any]]] = []
    for path in paths:
        print()
        print(f"=== {path.stem}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            summary, warning = await summarize(data, settings)
        except Exception as exc:
            print(f"  불러오기 실패: {type(exc).__name__}: {exc}")
            failed += 1
            continue

        if summary is None:
            print(f"  요약 실패: {warning}")
            failed += 1
            continue

        violations = check(data, summary)
        for violation in violations:
            print(f"  [{violation.severity}] {violation.code}: {violation.message}")
        if not violations:
            print("  위반 없음")

        for note in summary["radius_notes"]:
            print(f"  {note['radius_m']}m: {note['text']}")
        for key in ("overall", "concentration"):
            if summary.get(key):
                print(f"  {key}: {summary[key]}")
        for note in summary["index_notes"]:
            print(f"  {note['label']}: {note['text']}")

        blocking = errors(violations)
        failed += len(blocking)
        if blocking and not args.force:
            print("  -> 오류가 있어 갱신 대상에서 뺍니다. 덮어쓰려면 --force 를 붙이세요.")
            continue

        data["summary"] = summary
        data["summary_text"] = render_summary_text(summary)
        data["summary_model"] = settings.llm_model
        ready.append((path, data))

    if not args.write:
        print()
        print("미리보기입니다. 내용을 확인한 뒤 --write 를 붙여 다시 돌리세요.")
        return 1 if failed else 0

    print()
    if len(ready) != len(paths) and not args.force:
        print(f"{len(paths)}건 중 {len(ready)}건만 통과해 아무것도 쓰지 않았습니다.")
        print("오류가 있는 것까지 덮어쓰려면 --force 를 붙이세요.")
        return 1

    for path, data in ready:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"-> {path.name} 갱신")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
