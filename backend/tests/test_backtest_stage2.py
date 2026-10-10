import asyncio
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from openai.types.chat import ChatCompletionMessage
from test_backtest_outcome import SEOUL_A, SEOUL_B, row

from app.agents.business_lifecycle.area_resolver import resolve_area
from app.agents.decision.llm import generate_decision
from app.agents.floating_population import baseline, classify
from app.agents.floating_population.client import quarter_code
from app.agents.floating_population.models import FlpopRecord, TrdarArea
from app.industries.catalog import SEOUL_TO_INDUSTRY
from app.llm import client as llm_client
from app.llm.client import LLMResponseError
from app.schemas import AgentAnalysis, AgentError, AnalysisTask, Scope
from app.seoul import previous_quarter
from backtest import stage2
from backtest.data import quarters_after, quarters_until
from backtest.mock import backtest_generate
from backtest.outcome import StoreTable
from backtest.population_baseline import load as load_baseline
from backtest.replay import load_areas, sample_areas, site_for
from backtest.stage2 import CallLimit, RawSaver, base_rates, run, summarize

BASE = "20234"
CODES = sorted(SEOUL_TO_INDUSTRY)[:8]
MISMATCH = "3001492"
RESOLVED_TO = "3120025"
LLM_ENV = {
    "DECISION_LLM_MODEL": "fake-model",
    "DECISION_LLM_API_KEY": "fake-key",
    "DECISION_LLM_BASE_URL": "http://127.0.0.1:9",
}


def synthetic(areas):
    quarters = quarters_until(BASE, 12) + quarters_after(BASE)
    rows = []
    for area in areas:
        for i, code in enumerate(CODES):
            for q in quarters:
                rows.append(row(q, area, code, 10 + i, i % 3 if q <= BASE else i))
    return pd.DataFrame(rows)


async def failed_population(task):
    return AgentAnalysis(
        request_id=task.request_id,
        agent_id="floating_population",
        status="error",
        error=AgentError(code="Offline", message="유동인구 자료를 받을 수 없습니다."),
    )


async def empty_population(task):
    return AgentAnalysis(
        request_id=task.request_id,
        agent_id="floating_population",
        status="no_data",
        scope=Scope(area="가상 상권", period="2023년 4분기"),
    )


class Counting:
    def __init__(self, result=None, error=None):
        self.calls, self.result, self.error = 0, result, error

    def __call__(self, system_prompt, input_json):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def bad_evidence(system_prompt, input_json):
    result = backtest_generate(system_prompt, input_json)
    result["recommendations"][0]["evidence"][0]["path"] = "/missing/path"
    return result


async def mock_request(messages, settings, *, tools, usage):
    produced = backtest_generate(messages[0]["content"], messages[1]["content"])
    return ChatCompletionMessage(role="assistant", content=json.dumps(produced, ensure_ascii=False))


def flpop(code, quarter):
    total = 920_000.0
    ages = {"10": 0.15, "20": 0.25, "30": 0.2, "40": 0.15, "50": 0.1, "60": 0.15}
    return FlpopRecord(
        trdar_cd=code,
        stdr_yyqu_cd=quarter,
        total=total,
        male=total / 2,
        female=total / 2,
        by_time={
            "00_06": 120_000.0,
            "06_11": 150_000.0,
            "11_14": 200_000.0,
            "14_17": 150_000.0,
            "17_21": 200_000.0,
            "21_24": 100_000.0,
        },
        by_day={
            **{d: 120_000.0 for d in ("mon", "tue", "wed", "thu", "fri")},
            "sat": 170_000.0,
            "sun": 150_000.0,
        },
        by_age={a: total * share for a, share in ages.items()},
    )


def fake_population_client(info):
    class FakeClient:
        opened: list = []

        def __init__(self, settings=None, http=None, today=None):
            self.today, self.closed = today, False
            FakeClient.opened.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            self.closed = True

        async def aclose(self):
            self.closed = True

        async def fetch_trdar_areas(self):
            return [
                TrdarArea(
                    trdar_cd=info.code,
                    trdar_cd_nm=info.name,
                    x=info.x,
                    y=info.y,
                    relm_ar=info.area_m2,
                    trdar_se_nm=info.kind,
                    adstrd_nm="가상동",
                )
            ]

        async def fetch_flpop_series(self, codes, quarters):
            code, series = quarter_code(self.today), []
            for _ in range(quarters):
                series.append((code, [flpop(c, code) for c in sorted(codes)]))
                code = previous_quarter(code)
            return series[::-1]

    return FakeClient


class StageTwoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.areas = load_areas()
        sample = sample_areas(cls.areas)
        cls.matched = [i for i in sample if resolve_area(site_for(i)).area_code == i.code][:2]

    def run_samples(self, infos, generate, out, extra=(), population=empty_population, **kw):
        data = synthetic([i.code for i in infos] + list(extra))
        build = stage2.build_agents

        def offline(data, info, base, population_agent=None):
            return build(data, info, base, population_agent=population)

        with patch.object(stage2, "build_agents", offline):
            return asyncio.run(run(data, infos, BASE, generate, Path(out), **kw))

    def records(self, out):
        return json.loads((Path(out) / "stage2_records.json").read_text(encoding="utf-8"))

    def test_population_error_is_recorded_and_stops_the_run(self):
        with tempfile.TemporaryDirectory() as out:
            summary = self.run_samples(
                self.matched, CallLimit(10, backtest_generate), out, population=failed_population
            )
            records = self.records(out)
        self.assertEqual(summary["stopped"], "agent_error")
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["status"], "ok")
        self.assertTrue(record["items"])
        self.assertIn("scored", [i["verdict"]["status"] for i in record["items"]])
        self.assertEqual(record["agents"]["floating_population"], "error")
        self.assertEqual(record["agents"]["commercial_area"], "ok")
        self.assertIn("business_lifecycle", record["agents"])
        self.assertEqual(
            record["agent_errors"],
            {"floating_population": "Offline: 유동인구 자료를 받을 수 없습니다."},
        )
        self.assertEqual(record["calls"], 1)
        self.assertEqual(summary["agent_status"]["floating_population"], {"error": 1})
        self.assertEqual(sum(summary["decision_status"].values()), 1)

    def test_healthy_run_records_statuses_calls_and_base_rates(self):
        meta = {"model": "backtest_mock", "llm": None}
        with tempfile.TemporaryDirectory() as out:
            summary = self.run_samples(
                self.matched, CallLimit(10, backtest_generate), out, meta=meta
            )
            records = self.records(out)
            self.assertFalse((Path(out) / "raw").exists())
        self.assertIsNone(summary["stopped"])
        self.assertEqual(len(records), 2)
        for record in records:
            self.assertEqual(record["status"], "ok")
            self.assertNotIn("error", record["agents"].values())
            self.assertEqual(record["agents"]["floating_population"], "no_data")
            self.assertEqual(record["agent_errors"], {})
            self.assertEqual(record["calls"], 1)
        self.assertEqual(summary["agent_status"]["commercial_area"], {"ok": 2})
        self.assertEqual(summary["model"], "backtest_mock")
        self.assertIsNone(summary["llm"])
        rates = summary["base_rates"]
        self.assertGreater(rates["cells"], 0)
        self.assertIsNone(rates["seoul_longer"])
        self.assertTrue(0 <= rates["area_longer"] <= 1)

    def test_mismatched_area_is_recorded_and_excluded(self):
        info = self.areas[MISMATCH]
        self.assertEqual(resolve_area(site_for(info)).area_code, RESOLVED_TO)
        generate = Counting()
        with tempfile.TemporaryDirectory() as out:
            summary = self.run_samples([info], generate, out)
            records = self.records(out)
        self.assertEqual(records[0]["status"], "area_mismatch")
        self.assertEqual(records[0]["resolved_area"], RESOLVED_TO)
        self.assertEqual(generate.calls, 0)
        self.assertEqual(summary["samples"], 1)
        self.assertEqual(summary["ok"], 0)
        self.assertEqual(summarize(records)["ok"], 0)

    def test_call_limit_stops_after_first_area(self):
        limit = CallLimit(1, backtest_generate)
        with tempfile.TemporaryDirectory() as out:
            summary = self.run_samples(self.matched, limit, out)
            records = self.records(out)
        self.assertEqual([r["status"] for r in records], ["ok", "call_limit"])
        self.assertEqual(records[0]["area"]["code"], self.matched[0].code)
        self.assertEqual(records[1]["area"]["code"], self.matched[1].code)
        self.assertEqual(records[1]["calls"], 0)
        self.assertEqual(summary["stopped"], "call_limit")
        self.assertEqual(summary["ok"], 1)

    def test_call_limit_hit_on_correction_retry_keeps_the_calls_it_used(self):
        generate = CallLimit(1, bad_evidence)
        with tempfile.TemporaryDirectory() as out:
            summary = self.run_samples(self.matched, generate, out)
            records = self.records(out)
        self.assertEqual(summary["stopped"], "call_limit")
        self.assertEqual([r["status"] for r in records], ["call_limit"])
        self.assertEqual(records[0]["calls"], 1)
        self.assertEqual(summary["errors"], 0)
        self.assertEqual(generate.calls, 1)

    def test_summary_is_saved_after_every_area(self):
        snapshots = []
        folder = {}

        def capture(system_prompt, input_json):
            path = Path(folder["out"]) / "stage2_summary.json"
            snapshots.append(
                json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            )
            return backtest_generate(system_prompt, input_json)

        with tempfile.TemporaryDirectory() as out:
            folder["out"] = out
            summary = self.run_samples(self.matched, CallLimit(10, capture), out)
        self.assertIsNone(snapshots[0])
        self.assertEqual(snapshots[1]["stopped"], "incomplete")
        self.assertEqual(snapshots[1]["samples"], 1)
        self.assertIsNone(summary["stopped"])

    def test_model_input_never_mentions_the_backtest(self):
        seen = []

        def capture(system_prompt, input_json):
            seen.append(input_json)
            return backtest_generate(system_prompt, input_json)

        with tempfile.TemporaryDirectory() as out:
            self.run_samples(self.matched[:1], CallLimit(10, capture), out)
        self.assertTrue(seen)
        for text in seen:
            self.assertNotIn("백테스트", text)
            self.assertNotIn("backtest", text.casefold())

    def test_areas_that_resolve_elsewhere_are_dropped_before_sampling(self):
        settings = stage2.lifecycle_settings(BASE)
        picked = {code: self.areas[code] for code in (MISMATCH, self.matched[0].code)}
        self.assertEqual(list(stage2.resolvable_areas(picked, settings)), [self.matched[0].code])

    def test_repeated_identical_errors_stop_the_run(self):
        sample = sample_areas(self.areas)
        infos = [i for i in sample if resolve_area(site_for(i)).area_code == i.code][:4]
        with tempfile.TemporaryDirectory() as out:
            summary = self.run_samples(infos, Counting(error=RuntimeError("boom")), out)
            records = self.records(out)
        self.assertEqual(summary["stopped"], "repeated_error")
        self.assertEqual([r["status"] for r in records], ["error"] * 3)
        self.assertEqual(summary["errors"], 3)
        self.assertEqual(summary["error_types"], {records[0]["error"]: 3})

    def test_keep_going_records_every_error_without_stopping(self):
        sample = sample_areas(self.areas)
        infos = [i for i in sample if resolve_area(site_for(i)).area_code == i.code][:4]
        with tempfile.TemporaryDirectory() as out:
            summary = self.run_samples(
                infos, Counting(error=RuntimeError("boom")), out, keep_going=True
            )
            records = self.records(out)
        self.assertIsNone(summary["stopped"])
        self.assertTrue(summary["keep_going"])
        self.assertEqual([r["status"] for r in records], ["error"] * 4)

    def test_decision_contract_failure_keeps_diagnostics(self):
        with tempfile.TemporaryDirectory() as out:
            self.run_samples(self.matched[:1], CallLimit(10, bad_evidence), out)
            record = self.records(out)[0]
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["error"], "DecisionContractError")
        self.assertEqual(record["code"], "DECISION_CONTRACT_INVALID")
        self.assertEqual(record["diagnostics"]["stage"], "decision_validation")
        self.assertEqual(len(record["failures"]), 2)
        first = record["failures"][0]
        self.assertEqual(first["invalid_path"], "/missing/path")
        self.assertIn("candidates", first)
        self.assertIn("reason", first)
        self.assertEqual(record["calls"], 2)
        self.assertEqual(record["agents"]["commercial_area"], "ok")

    def test_llm_error_keeps_code_and_diagnostics(self):
        error = LLMResponseError("LLM_SCHEMA_INVALID", fields=["summary"], schema="DecisionContent")
        with tempfile.TemporaryDirectory() as out:
            self.run_samples(self.matched[:1], Counting(error=error), out)
            record = self.records(out)[0]
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["code"], "LLM_SCHEMA_INVALID")
        self.assertEqual(
            record["diagnostics"], {"fields": ["summary"], "schema": "DecisionContent"}
        )

    def test_missing_population_baseline_stops_before_any_call(self):
        generate = Counting()
        data = synthetic([i.code for i in self.matched])
        with tempfile.TemporaryDirectory() as out, self.assertRaises(FileNotFoundError) as caught:
            asyncio.run(run(data, self.matched, "20241", generate, Path(out)))
        self.assertIn("20241", str(caught.exception))
        self.assertEqual(generate.calls, 0)

    def test_population_input_uses_as_of_t_baseline(self):
        info = self.matched[0]
        label, student = baseline.BASELINE_LABEL, classify.STUDENT_MIN
        agents = stage2.build_agents(synthetic([info.code]), info, BASE)
        task = AnalysisTask(request_id="req-pop", site=site_for(info), radius_m=500)
        client = fake_population_client(info)
        with patch.object(stage2, "SeoulOpenDataClient", client):
            analysis = asyncio.run(agents["floating_population"](task))
        self.assertIn(analysis.status, {"ok", "partial"})
        text = json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False)
        self.assertNotIn("2026", text)
        benchmark = analysis.data["benchmark"]
        self.assertIn("2023년 4분기", benchmark["baseline"])
        values = load_baseline(BASE)
        self.assertEqual(
            analysis.data["type"]["thresholds"]["age_10_min"],
            round(values["SEOUL_AVG"]["age_10"] + classify.MARGIN, 4),
        )
        self.assertEqual(
            benchmark["age_index"]["10"], round(0.15 / values["AGE_SHARE_AVG"]["10"], 3)
        )
        self.assertEqual((baseline.BASELINE_LABEL, classify.STUDENT_MIN), (label, student))
        self.assertEqual([c.today.isoformat() for c in client.opened], ["2023-12-31"])
        self.assertTrue(all(c.closed for c in client.opened))

    def test_lifecycle_settings_ignore_env_overrides(self):
        env = {
            "BUSINESS_LIFECYCLE_AREA_CODE": "9999999",
            "BUSINESS_LIFECYCLE_AREA_NAME": "다른 상권",
            "BUSINESS_LIFECYCLE_QUARTER_COUNT": "4",
        }
        with patch.dict(os.environ, env):
            settings = stage2.lifecycle_settings(BASE)
        self.assertEqual(settings.base_quarter_override, BASE)
        self.assertEqual(settings.quarter_count, 12)
        self.assertIsNone(settings.area_code_override)
        self.assertIsNone(settings.area_name_override)

    def test_llm_meta_names_settings_without_secrets(self):
        env = {**LLM_ENV, "DECISION_LLM_MAX_TOKENS": "4096", "DECISION_LLM_REASONING_EFFORT": "low"}
        with patch.dict(os.environ, env):
            meta = stage2.llm_meta(mock=False)
        self.assertEqual(
            meta,
            {
                "model": "fake-model",
                "llm": {"model": "fake-model", "max_tokens": 4096, "reasoning_effort": "low"},
            },
        )
        self.assertNotIn("fake-key", json.dumps(meta))
        self.assertEqual(stage2.llm_meta(mock=True), {"model": "backtest_mock", "llm": None})

    def test_save_raw_writes_every_model_reply_of_the_run(self):
        original = llm_client._complete
        with (
            tempfile.TemporaryDirectory() as out,
            patch.dict(os.environ, LLM_ENV),
            patch.object(llm_client, "_request", mock_request),
        ):
            summary = self.run_samples(self.matched, CallLimit(10), out, save_raw=True)
            raw = Path(out) / "raw"
            names = sorted(p.name for p in raw.iterdir())
            first = json.loads((raw / names[0]).read_text(encoding="utf-8"))
        self.assertEqual(summary["ok"], 2)
        self.assertEqual(names, sorted(f"site-{i.code}-{BASE}_1.txt" for i in self.matched))
        self.assertIn("recommendations", first)
        self.assertIs(llm_client._complete, original)


class RawSaverTests(unittest.IsolatedAsyncioTestCase):
    async def test_raw_text_is_saved_even_when_json_parsing_fails(self):
        replies = iter(["{not json", '{"status": "no_data"}'])

        async def fake_request(messages, settings, *, tools, usage):
            return ChatCompletionMessage(role="assistant", content=next(replies))

        original = llm_client._complete
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, LLM_ENV),
            patch.object(llm_client, "_request", fake_request),
        ):
            saver = RawSaver(Path(tmp) / "raw")
            saver.request_id = "backtest-1-20234"
            with saver.active():
                with self.assertRaises(LLMResponseError) as caught:
                    await generate_decision("system", "{}")
                self.assertEqual(caught.exception.code, "LLM_INVALID_JSON")
                with self.assertRaises(LLMResponseError):
                    await generate_decision("system", "{}")
            first = (Path(tmp) / "raw" / "backtest-1-20234_1.txt").read_text(encoding="utf-8")
            second = (Path(tmp) / "raw" / "backtest-1-20234_2.txt").read_text(encoding="utf-8")
        self.assertEqual(first, "{not json")
        self.assertEqual(second, '{"status": "no_data"}')
        self.assertIs(llm_client._complete, original)


class MainGuardTests(unittest.TestCase):
    def test_real_run_needs_explicit_size_and_limit(self):
        with tempfile.TemporaryDirectory() as out, patch.object(stage2, "load_environment") as env:
            for extra in ([], ["--n", "2"], ["--limit", "4"]):
                with self.subTest(extra=extra), self.assertRaises(SystemExit):
                    with redirect_stderr(io.StringIO()):
                        stage2.main(["--data", out, "--out", out, "--real", *extra])
            env.assert_not_called()

    def test_existing_results_are_never_overwritten(self):
        for name in ("stage2_records.json", "stage2_summary.json"):
            with (
                tempfile.TemporaryDirectory() as out,
                patch.object(stage2, "load_environment") as env,
            ):
                (Path(out) / name).write_text("[]", encoding="utf-8")
                with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                    stage2.main(["--data", out, "--out", out, "--mock"])
                env.assert_not_called()
                self.assertEqual((Path(out) / name).read_text(encoding="utf-8"), "[]")


class BaseRateTests(unittest.TestCase):
    def test_ties_are_left_out_of_base_rates(self):
        table = StoreTable(
            pd.DataFrame(
                [
                    row(BASE, "1", SEOUL_A, 10, 0),
                    row(BASE, "1", SEOUL_B, 10, 0),
                    row(BASE, "2", SEOUL_A, 10, 0),
                    row("20241", "1", SEOUL_A, 10, 0),
                    row("20241", "1", SEOUL_B, 10, 5),
                    row("20241", "2", SEOUL_A, 10, 2),
                ]
            )
        )
        rates = base_rates(table, ["1", "2"], BASE, ["20241"])
        self.assertEqual(rates, {"seoul_longer": 0.5, "area_longer": 0.5, "cells": 3})

    def test_base_rates_cover_every_scorable_cell(self):
        table = StoreTable(
            pd.DataFrame(
                [
                    row(BASE, "1", SEOUL_A, 10, 0),
                    row(BASE, "2", SEOUL_A, 20, 0),
                    row(BASE, "1", SEOUL_B, 2, 0),
                    row("20241", "1", SEOUL_A, 10, 1),
                    row("20242", "1", SEOUL_A, 0, 0),
                    row("20243", "1", SEOUL_A, 10, 2),
                    row("20241", "2", SEOUL_A, 20, 10),
                    row("20243", "2", SEOUL_A, 20, 10),
                    row("20241", "1", SEOUL_B, 2, 0),
                    row("20243", "1", SEOUL_B, 2, 0),
                ]
            )
        )
        quarters = ["20241", "20242", "20243"]
        rates = base_rates(table, ["1", "2", "1"], BASE, quarters)
        self.assertEqual(rates, {"seoul_longer": 0.5, "area_longer": 0.0, "cells": 2})
        self.assertIsNone(base_rates(table, ["9"], BASE, quarters))


if __name__ == "__main__":
    unittest.main()
