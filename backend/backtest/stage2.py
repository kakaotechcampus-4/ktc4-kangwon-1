import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable, Iterable, Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd

from app.agents.business_lifecycle import agent as lifecycle
from app.agents.business_lifecycle.area_resolver import BusinessAreaNoDataError, resolve_area
from app.agents.business_lifecycle.config import Settings as LifecycleSettings
from app.agents.decision.llm import generate_decision
from app.agents.floating_population import agent as population
from app.agents.floating_population.client import SeoulOpenDataClient
from app.agents.floating_population.config import Settings as PopulationSettings
from app.agents.orchestration.graph import RunHooks, run_graph
from app.agents.orchestration.workflow import AgentRegistry
from app.config import load_environment
from app.llm import client as llm_client
from app.llm.config import LLMSettings
from app.schemas import AgentAnalysis, AnalysisTask, DecisionResult, Site
from backtest import population_baseline
from backtest.data import load_store_data, quarters_after
from backtest.mock import MOCK_MODEL, backtest_generate
from backtest.outcome import StoreTable, Verdict
from backtest.replay import (
    AreaInfo,
    commercial_substitute,
    load_areas,
    quarter_end,
    replay_store_rows,
    sample_areas,
    site_for,
)
from backtest.scores import bootstrap_mean, cluster_bootstrap_ratio

REPEATED_ERRORS = 3


class CallLimitReached(RuntimeError):
    pass


class CallLimit:
    def __init__(self, limit: int, generate: Callable[..., Any] = generate_decision):
        self.limit, self.calls, self.generate = limit, 0, generate
        self.tripped = False

    async def __call__(self, system_prompt: str, input_json: str) -> Any:
        if self.calls >= self.limit:
            self.tripped = True
            raise CallLimitReached(f"모델 호출 상한 {self.limit}회에 도달했습니다.")
        self.calls += 1
        result = self.generate(system_prompt, input_json)
        return await result if hasattr(result, "__await__") else result


class RawSaver:
    def __init__(self, folder: Path):
        self.folder = folder
        self.request_id = "unknown"
        self.counts: Counter[str] = Counter()

    @contextmanager
    def active(self) -> Iterator[None]:
        original = llm_client._complete

        async def complete(
            messages: list[Any], settings: LLMSettings, *, tools: list[Any] | None = None
        ) -> Any:
            self.counts[self.request_id] += 1
            path = self.folder / f"{self.request_id}_{self.counts[self.request_id]}.txt"
            message = await original(messages, settings, tools=tools)
            self.folder.mkdir(parents=True, exist_ok=True)
            path.write_text(message.content or "", encoding="utf-8")
            return message

        with patch.object(llm_client, "_complete", complete):
            yield


def lifecycle_settings(base: str) -> LifecycleSettings:
    return LifecycleSettings.from_env(
        base_quarter_override=base,
        quarter_count=12,
        area_code_override=None,
        area_name_override=None,
    )


def llm_meta(*, mock: bool) -> dict:
    if mock:
        return {"model": MOCK_MODEL, "llm": None}
    settings = LLMSettings.from_env("DECISION")
    return {
        "model": settings.model,
        "llm": {
            "model": settings.model,
            "max_tokens": settings.max_tokens,
            "reasoning_effort": settings.reasoning_effort,
        },
    }


def request_id_for(info: AreaInfo, base: str) -> str:
    return f"site-{info.code}-{base}"


def resolvable_areas(
    areas: dict[str, AreaInfo], settings: LifecycleSettings
) -> dict[str, AreaInfo]:
    kept = {}
    for code, info in areas.items():
        try:
            resolved = resolve_area(site_for(info), settings)
        except BusinessAreaNoDataError:
            continue
        if resolved.area_code == code:
            kept[code] = info
    return kept


def agent_fields(analyses: Iterable[AgentAnalysis]) -> dict:
    agents: dict[str, str] = {}
    errors: dict[str, str] = {}
    for analysis in analyses:
        agents[analysis.agent_id] = analysis.status
        if analysis.status == "error":
            detail = analysis.error
            text = f"{detail.code}: {detail.message}" if detail else "사유 없음"
            errors[analysis.agent_id] = text[:200]
    return {"agents": agents, "agent_errors": errors}


def error_fields(error: BaseException) -> dict:
    fields: dict[str, Any] = {"error": type(error).__name__, "message": str(error)[:300]}
    for source in (error, error.__cause__):
        for name in ("code", "diagnostics", "failures"):
            value = getattr(source, name, None)
            if value is None or name in fields or (name == "code" and not isinstance(value, str)):
                continue
            fields[name] = json.loads(json.dumps(value, ensure_ascii=False, default=str))
    return fields


def build_agents(
    data: pd.DataFrame,
    info: AreaInfo,
    base: str,
    *,
    population_agent: Callable[[AnalysisTask], Awaitable[AgentAnalysis]] | None = None,
) -> AgentRegistry:
    async def run_lifecycle(task: AnalysisTask) -> AgentAnalysis:
        with replay_store_rows(data, base):
            return await lifecycle.analyze(task, settings=lifecycle_settings(base))

    async def run_population(task: AnalysisTask) -> AgentAnalysis:
        values = population_baseline.load(base)
        settings = PopulationSettings.from_env()
        async with SeoulOpenDataClient(settings, today=quarter_end(base)) as client:
            with (
                patch.object(population, "load_snapshot", return_value=[]),
                population_baseline.as_of(values),
            ):
                return await population.analyze(task, client=client)

    async def run_commercial(task: AnalysisTask) -> AgentAnalysis:
        return commercial_substitute(data, info, base, task.request_id)

    return {
        "business_lifecycle": run_lifecycle,
        "floating_population": population_agent or run_population,
        "commercial_area": run_commercial,
    }


async def run_sample(
    data: pd.DataFrame,
    table: StoreTable,
    info: AreaInfo,
    base: str,
    generate: Callable[..., Any],
    *,
    population_agent: Callable[[AnalysisTask], Awaitable[AgentAnalysis]] | None = None,
    seen: dict[str, AgentAnalysis] | None = None,
) -> dict:
    site = site_for(info)

    async def resolve(_: str) -> Site:
        return site

    async def completed(analysis: AgentAnalysis) -> None:
        if seen is not None:
            seen[analysis.agent_id] = analysis

    record: dict = {"area": asdict(info), "base": base}
    resolved = resolve_area(site, lifecycle_settings(base))
    if resolved.area_code != info.code:
        return {**record, "status": "area_mismatch", "resolved_area": resolved.area_code}
    result = await run_graph(
        info.name,
        resolve=resolve,
        agents=build_agents(data, info, base, population_agent=population_agent),
        radius_m=500,
        request_id=request_id_for(info, base),
        generate=generate,
        supplements=None,
        allow_questions=False,
        map_lookup=None,
        hooks=RunHooks(on_analysis_completed=completed),
        mode="single_decision",
    )
    if not isinstance(result, DecisionResult):
        return {**record, "status": "waiting"}
    future = quarters_after(base)
    judged = []
    for kind, items in (
        ("recommended", result.recommendations),
        ("not_recommended", result.not_recommended),
    ):
        for item in items:
            verdict = table.judge(info.code, item.category.code or "", kind, base, future)
            judged.append(
                {
                    "kind": kind,
                    "industry": item.category.code,
                    "name": item.category.middle,
                    "score": item.score,
                    "reasons": item.reasons,
                    "verdict": asdict(verdict),
                }
            )
    record.update(
        status="ok",
        decision_status=result.status,
        **agent_fields(result.source_analyses),
        items=judged,
        limitations=result.limitations,
    )
    return record


def base_cells(table: StoreTable, code: str, base: str, quarters: list[str]) -> list[Verdict]:
    return [
        verdict
        for industry in sorted(table.industries)
        if (verdict := table.judge(code, industry, "recommended", base, quarters)).status
        == "scored"
    ]


def base_rates(
    table: StoreTable,
    codes: list[str],
    base: str,
    quarters: list[str],
    cache: dict[str, list[Verdict]] | None = None,
) -> dict | None:
    cache = {} if cache is None else cache
    cells = []
    for code in dict.fromkeys(codes):
        if code not in cache:
            cache[code] = base_cells(table, code, base, quarters)
        cells.extend(cache[code])
    if not cells:
        return None

    def longer(name: str) -> float | None:
        known = [getattr(v, name) for v in cells if getattr(v, name) is not None]
        return sum(known) / len(known) if known else None

    return {
        "seoul_longer": longer("correct_vs_seoul"),
        "area_longer": longer("correct_vs_area"),
        "cells": len(cells),
    }


def summarize(records: list[dict]) -> dict:
    done = [r for r in records if r.get("status") == "ok"]
    allitems = [i for r in done for i in r["items"]]
    errors = [r for r in records if r.get("status") == "error"]
    summary: dict = {"samples": len(records), "ok": len(done), "interval_unit": "site"}
    for ref in ("seoul", "area"):
        key = f"correct_vs_{ref}"
        for kind in ("recommended", "not_recommended"):
            groups = [
                [
                    1.0 if i["verdict"][key] else 0.0
                    for i in r["items"]
                    if i["kind"] == kind
                    and i["verdict"]["status"] == "scored"
                    and i["verdict"][key] is not None
                ]
                for r in done
            ]
            groups = [group for group in groups if group]
            summary[f"{kind}_{key}"] = cluster_bootstrap_ratio(groups) if groups else None
    gaps = []
    for r in records:
        if r.get("status") != "ok":
            continue
        rec = [
            i["verdict"]["survival"]
            for i in r["items"]
            if i["kind"] == "recommended" and i["verdict"]["status"] == "scored"
        ]
        non = [
            i["verdict"]["survival"]
            for i in r["items"]
            if i["kind"] == "not_recommended" and i["verdict"]["status"] == "scored"
        ]
        if rec and non:
            gaps.append(sum(rec) / len(rec) - sum(non) / len(non))
    summary["recommended_minus_not"] = bootstrap_mean(gaps) if gaps else None
    for status in ("pending", "absent", "unscorable"):
        summary[f"{status}_ratio"] = (
            (sum(i["verdict"]["status"] == status for i in allitems) / len(allitems))
            if allitems
            else None
        )
    absent: dict[str, float | None] = {}
    for kind in ("recommended", "not_recommended"):
        items = [i for i in allitems if i["kind"] == kind]
        absent[kind] = (
            sum(i["verdict"]["status"] == "absent" for i in items) / len(items) if items else None
        )
    summary["absent_ratio_by_kind"] = absent
    summary["errors"] = len(errors)
    summary["error_types"] = dict(Counter(r["error"] for r in errors))
    agent_status: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for r in records:
        for agent_id, status in (r.get("agents") or {}).items():
            agent_status[agent_id][status] += 1
    summary["agent_status"] = {key: dict(value) for key, value in agent_status.items()}
    summary["decision_status"] = dict(
        Counter(r["decision_status"] for r in records if r.get("status") == "ok")
    )
    return summary


async def run(
    data: pd.DataFrame,
    samples: list[AreaInfo],
    base: str,
    generate: Callable[..., Any],
    out: Path,
    *,
    meta: dict | None = None,
    save_raw: bool = False,
    keep_going: bool = False,
) -> dict:
    population_baseline.load(base)
    table = StoreTable(data)
    records: list[dict] = []
    stopped = None
    streak: list[str] = []
    checked = False
    cache: dict[str, list[Verdict]] = {}

    def save(reason: str | None) -> dict:
        (out / "stage2_records.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary = summarize(records)
        ok_codes = [r["area"]["code"] for r in records if r.get("status") == "ok"]
        summary.update(
            stopped=reason,
            calls=getattr(generate, "calls", None),
            created=date.today().isoformat(),
            base_rates=base_rates(table, ok_codes, base, quarters_after(base), cache),
            keep_going=keep_going,
            **(meta or {}),
        )
        (out / "stage2_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return summary

    saver = RawSaver(out / "raw") if save_raw else None
    with saver.active() if saver else nullcontext():
        for info in samples:
            seen: dict[str, AgentAnalysis] = {}
            before = getattr(generate, "calls", None)
            if saver:
                saver.request_id = request_id_for(info, base)
            try:
                record = await run_sample(data, table, info, base, generate, seen=seen)
            except CallLimitReached:
                record = {"area": asdict(info), "base": base, "status": "call_limit"}
            except Exception as error:
                record = {
                    "area": asdict(info),
                    "base": base,
                    "status": "error",
                    **error_fields(error),
                }
                if seen:
                    record.update(agent_fields(seen.values()))
            if getattr(generate, "tripped", False):
                record = {**record, "status": "call_limit"}
            if before is not None:
                record["calls"] = getattr(generate, "calls", before) - before
            records.append(record)
            if record["status"] == "call_limit":
                stopped = "call_limit"
                break
            if not checked and "agents" in record:
                checked = True
                if "error" in record["agents"].values():
                    stopped = "agent_error"
                    break
            streak = (
                [*streak, record["error"]][-REPEATED_ERRORS:] if record["status"] == "error" else []
            )
            if not keep_going and len(streak) == REPEATED_ERRORS and len(set(streak)) == 1:
                stopped = "repeated_error"
                break
            save("incomplete")
    return save(stopped)


def main(argv: list[str] | None = None) -> int:
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base", default="20234")
    parser.add_argument("--n", type=int)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mock", action="store_true")
    mode.add_argument("--real", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--save-raw", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    args = parser.parse_args(argv)
    if args.real and (args.n is None or args.limit is None):
        parser.error("--real 실행은 --n과 --limit를 직접 정해야 합니다.")
    existing = [
        name
        for name in ("stage2_records.json", "stage2_summary.json")
        if (args.out / name).exists()
    ]
    if existing:
        parser.error(f"{args.out}에 이전 결과({', '.join(existing)})가 있습니다. 새 폴더를 쓰세요.")
    load_environment()
    population_baseline.load(args.base)
    args.out.mkdir(parents=True, exist_ok=True)
    limit = 120 if args.limit is None else args.limit
    generate = CallLimit(limit, backtest_generate if args.mock else generate_decision)
    areas = resolvable_areas(load_areas(), lifecycle_settings(args.base))
    samples = sample_areas(areas, n=40 if args.n is None else args.n)
    asyncio.run(
        run(
            load_store_data(args.data),
            samples,
            args.base,
            generate,
            args.out,
            meta=llm_meta(mock=args.mock),
            save_raw=args.save_raw,
            keep_going=args.keep_going,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
