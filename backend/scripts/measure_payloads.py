"""저장 실행의 자료로 현재 전문가 입력을 재구성합니다. 모델·외부 API는 호출하지 않습니다."""

import argparse
import asyncio
import cProfile
import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.decision.context import build_context
from app.agents.orchestration.consult import build_specialist_tools
from app.agents.specialists.agent import answer_query, write_brief
from app.schemas import (
    AgentAnalysis,
    AgentBrief,
    AnalysisTask,
    DecisionRequest,
    MapObservation,
    SpecialistAnswer,
)


def load_run(directory: Path):
    """원본 실행 DB를 읽기 전용으로 열어 당시 자료를 가져옵니다."""
    with sqlite3.connect(
        (directory / "analysis.sqlite3").resolve().as_uri() + "?mode=ro", uri=True
    ) as db:
        db.row_factory = sqlite3.Row
        row = dict(db.execute("SELECT * FROM analysis_requests").fetchone())
        analyses = [
            AgentAnalysis.model_validate_json(r[0])
            for r in db.execute("SELECT analysis_json FROM agent_results ORDER BY attempt,agent_id")
        ]
        briefs = [
            AgentBrief.model_validate_json(r[0])
            for r in db.execute("SELECT brief_json FROM agent_briefs ORDER BY agent_id")
        ]
        answers = [
            SpecialistAnswer.model_validate_json(r[0])
            for r in db.execute(
                "SELECT answer_json FROM specialist_consults ORDER BY round,agent_id"
            )
        ]
        maps = [
            MapObservation.model_validate_json(r[0])
            for r in db.execute(
                "SELECT observation_json FROM map_observations "
                "WHERE observation_json IS NOT NULL ORDER BY attempt"
            )
        ]
    task = AnalysisTask(
        request_id=row["request_id"], site=json.loads(row["site_json"]), radius_m=row["radius_m"]
    )
    return task, analyses, briefs, answers, maps


async def capture_payload(operation, *args, **kwargs):
    """실제 전문가 진입점이 생성기에 전달한 첫 JSON 입력을 캡처합니다."""
    payload = None

    async def generate(messages, definitions):
        nonlocal payload
        payload = messages[1]["content"]
        return {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "measure",
                    "type": "function",
                    "function": {
                        "name": "finish",
                        "arguments": json.dumps(
                            {"headline": "측정", "findings": [], "limitations": []}
                        ),
                    },
                }
            ],
        }

    await operation(*args, generate=generate, max_steps=1, **kwargs)
    assert payload is not None
    return payload


def size(role, content):
    value = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return {"role": role, "chars": len(value), "json_bytes": len(value.encode("utf-8"))}


async def measure(directory: Path):
    task, analyses, briefs, answers, maps = await asyncio.to_thread(load_run, directory)
    first, latest = {}, {}
    for analysis in analyses:
        first.setdefault(analysis.agent_id, analysis)
        latest[analysis.agent_id] = analysis
    rows = []
    for role, analysis in first.items():
        rows.append(
            size("brief." + role, await capture_payload(write_brief, task, analysis, tools={}))
        )
    for answer in answers:
        role = answer.query.agent_id
        rows.append(
            size(
                "answer." + role,
                await capture_payload(
                    answer_query,
                    task,
                    answer.query,
                    answer.round,
                    analysis=latest.get(role),
                    observation=maps[-1] if maps else None,
                    tools={},
                ),
            )
        )
    if maps:
        snapshots = iter(maps)

        async def lookup(task, plan):
            return next(snapshots)

        question = next(a.query for a in answers if a.query.agent_id == "map_analysis")
        hooks = SimpleNamespace(
            on_supplement=None, on_map_requested=None, on_map_completed=None, on_map_result=None
        )
        tools, _ = build_specialist_tools(
            task,
            "map_analysis",
            analyses=list(latest.values()),
            supplements=[],
            map_lookup=lookup,
            hooks=hooks,
            state={},
            query=question,
        )
        for i, observation in enumerate(maps, 1):
            query = list(observation.data.queries.values())[-1].request
            name = "search_industry" if query.kind == "industry" else "search_facility"
            arguments = (
                {"code": query.industry_code, "query": query.query}
                if query.kind == "industry"
                else {"code": query.facility_code}
            )
            rows.append(size(f"map_tool.{i}", await tools[name].execute(arguments)))
    request = DecisionRequest(
        request_id=task.request_id,
        address=task.site.input_address,
        analyses=list(latest.values()),
        map_observation=maps[-1] if maps else None,
    )
    profiler = cProfile.Profile()
    profiler.runcall(build_context, request, briefs=briefs, answers=answers)
    timing = []
    for _ in range(10):
        start = time.perf_counter()
        build_context(request, briefs=briefs, answers=answers)
        timing.append((time.perf_counter() - start) * 1000)
    stats = profiler.getstats()
    counts = {
        name: sum(
            r.callcount
            for r in stats
            if not isinstance(r.code, str)
            and r.code.co_name == name
            and r.code.co_filename.replace("\\", "/").endswith("evidence/index.py")
        )
        for name in ("index_paths", "build")
    }
    return {
        "run": task.request_id,
        "rows": rows,
        "context_ms_median": round(statistics.median(timing), 3),
        "index_paths_calls": counts["index_paths"],
        "source_index_builds": counts["build"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--json", action="store_true", help="비교용 JSON 출력")
    args = parser.parse_args()
    result = asyncio.run(measure(args.run_directory))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print("| 역할 | 글자 수 | JSON UTF-8 바이트 |")
    print("| --- | ---: | ---: |")
    for row in result["rows"]:
        print(f"| {row['role']} | {row['chars']} | {row['json_bytes']} |")
    print(
        f"build_context 중앙값: {result['context_ms_median']}ms; "
        f"index_paths: {result['index_paths_calls']}회; "
        f"SourceIndex.build: {result['source_index_builds']}회"
    )


if __name__ == "__main__":
    main()
