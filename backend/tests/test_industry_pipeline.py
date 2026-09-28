"""원본 건수부터 공통 업종 출력까지의 계약을 검사합니다."""

import asyncio
import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from test_commercial_area_agent import MASTER, SITE, FakeClient, sample_stores

from app.agents.business_lifecycle.agent import run_business_lifecycle_agent
from app.agents.business_lifecycle.client import get_recent_quarters, normalize_row
from app.agents.business_lifecycle.formatter import (
    BusinessLifecycleFormatterError,
    format_for_mediator,
)
from app.agents.business_lifecycle.input_builder import build_agent_input
from app.agents.business_lifecycle.preprocess import preprocess_business_lifecycle_data
from app.agents.business_lifecycle.scoring import calculate_lifecycle_scores
from app.agents.commercial_area.agent import analyze
from app.agents.commercial_area.config import Settings
from app.agents.commercial_area.industries import load_middle_master, write_master
from app.agents.decision import analyze as decide
from app.industries import lookup
from app.industries.catalog import INDUSTRIES
from app.schemas import AgentAnalysis, AnalysisTask, DecisionRequest


def raw_rows(quarters=("20241", "20242", "20243", "20244")):
    # I210 네 원천을 합치면 분기당 점포 100, 폐업 10: 비율 평균 25%가 아닌 10%.
    return [
        normalize_row(
            {
                "STDR_YYQU_CD": quarter,
                "TRDAR_CD": "3120240",
                "SVC_INDUTY_CD": code,
                "SVC_INDUTY_CD_NM": code,
                "SIMILR_INDUTY_STOR_CO": stores,
                "STOR_CO": stores,
                "FRC_STOR_CO": 0,
                "OPBIZ_STOR_CO": 0,
                "CLSBIZ_STOR_CO": closed,
                "OPBIZ_RT": 0,
                "CLSBIZ_RT": 0,
            }
        )
        for quarter in quarters
        for code, stores, closed in (
            ("CS100005", 10, 10),
            ("CS100006", 30, 0),
            ("CS100007", 30, 0),
            ("CS100008", 30, 0),
            ("CS100001", 20, 0),
        )
    ]


def preprocess(rows):
    with patch(
        "app.agents.business_lifecycle.preprocess.fetch_recent_store_data", return_value=rows
    ):
        return preprocess_business_lifecycle_data("3120240", "20244", 4)


class IndustryPipelineTests(unittest.TestCase):
    def test_lookup_support_matches_mapping(self):
        self.assertTrue(lookup.get("I201").has_seoul)
        self.assertFalse(lookup.get("I205").has_seoul)

    def test_raw_counts_are_combined_before_rates_and_scores(self):
        frame = preprocess(raw_rows())
        self.assertEqual(set(frame.service_id), set(INDUSTRIES))
        row = frame.set_index("service_id").loc["I210"]
        self.assertEqual(row.period_close_count, 40)
        self.assertEqual(row.latest_store_count, 100)
        self.assertEqual(row.avg_close_rate, 10)
        scored = calculate_lifecycle_scores(frame, 4).set_index("service_id")
        self.assertEqual(scored.loc["I210", "lifecycle_score"], 55)
        self.assertEqual(scored.loc["I201", "lifecycle_score"], 95)

    def test_identical_duplicates_do_not_inflate_counts(self):
        rows = raw_rows()
        frame = preprocess(rows + [copy.deepcopy(rows[0])])
        self.assertEqual(frame.period_close_count.sum(), 40)

    def test_conflicting_duplicates_are_rejected(self):
        rows = raw_rows()
        duplicate = dict(rows[0], opbiz_stor_co=123)
        with self.assertRaisesRegex(ValueError, "중복"):
            preprocess(rows + [duplicate])

    def test_other_request_scope_and_unknown_codes_are_rejected(self):
        for change in (
            {"trdar_cd": "elsewhere"},
            {"stdr_yyqu_cd": "20234"},
            {"svc_induty_cd": "UNKNOWN"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                preprocess([dict(raw_rows()[0], **change)])

    def test_malformed_numbers_are_not_observed_zero(self):
        for bad in ("broken", "", float("inf"), -1, 1.5, True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                preprocess([dict(raw_rows()[0], opbiz_stor_co=bad)])

    def test_null_zero_missing_and_unsupported_remain_distinct(self):
        rows = raw_rows()
        for row in rows:
            if row["svc_induty_cd"] == "CS100001":
                row["similr_induty_stor_co"] = 0
            if row["svc_induty_cd"] == "CS100005":
                row["clsbiz_stor_co"] = None
        frame = preprocess(rows).set_index("service_id")
        self.assertIn("I201", frame.index)
        self.assertEqual(frame.loc["I201", "latest_store_count"], 0)
        self.assertTrue(pd.isna(frame.loc["I201", "avg_close_rate"]))
        self.assertTrue(pd.isna(frame.loc["I210", "period_close_count"]))
        self.assertEqual(frame.loc["I201", "data_status"], "observed")
        self.assertEqual(frame.loc["I202", "data_status"], "missing")
        self.assertEqual(frame.loc["I205", "data_status"], "unsupported")

    def test_missing_source_or_quarter_cannot_claim_complete_score(self):
        for rows in (
            [r for r in raw_rows() if r["svc_induty_cd"] != "CS100005"],
            [r for r in raw_rows() if r["stdr_yyqu_cd"] != "20242"],
        ):
            frame = preprocess(rows)
            self.assertIn("I210", set(frame.service_id))
            row = frame.set_index("service_id").loc["I210"]
            self.assertFalse(row.data_complete)
            score = calculate_lifecycle_scores(frame, 4).set_index("service_id")
            self.assertTrue(pd.isna(score.loc["I210", "lifecycle_score"]))

    def test_api_to_llm_to_formatter_uses_canonical_75_codes(self):
        def request_page(**kwargs):
            self.assertEqual(kwargs["area_code"], "3120240")
            self.assertEqual(kwargs["start_index"], 1)
            self.assertIn(kwargs["quarter"], ("20241", "20242", "20243", "20244"))
            rows = [
                {key.upper(): value for key, value in row.items()}
                for row in raw_rows()
                if row["stdr_yyqu_cd"] == kwargs["quarter"]
            ]
            return {
                "VwsmTrdarStorQq": {
                    "RESULT": {"CODE": "INFO-000"},
                    "list_total_count": len(rows),
                    "row": rows,
                }
            }

        async def completion(prompt, input_json, settings):
            payload = json.loads(input_json)
            body = {
                "industry_scores": [
                    dict(i, type="안정형", evidence=[], warning=None) for i in payload["industries"]
                ]
            }
            return body

        with (
            patch(
                "app.agents.business_lifecycle.client.request_page",
                side_effect=request_page,
            ),
            patch("app.agents.business_lifecycle.client.get_api_key", return_value="test-key"),
            patch("app.llm.client.complete_json", side_effect=completion),
        ):
            result = run_business_lifecycle_agent("3120240", "20244", 4, "pipeline-test")
        formatted = format_for_mediator(result)
        self.assertEqual({i["industry_id"] for i in formatted.data["industries"]}, set(INDUSTRIES))
        self.assertEqual(formatted.data["taxonomy"]["id"], "sbiz-middle-75")
        snack = next(i for i in formatted.data["industries"] if i["industry_id"] == "I210")
        self.assertEqual(snack["metrics"]["avg_close_rate"], 10)
        self.assertEqual(snack["score"], 55)
        self.assertTrue(
            any("53" in warning and "검수" in warning for warning in formatted.warnings)
        )
        for change in ({"industry_name": "잘못된 이름"}, {"industry_id": 1}, {"industry_id": True}):
            invalid = copy.deepcopy(result)
            invalid["industry_scores"][0].update(change)
            with self.subTest(change=change), self.assertRaises(BusinessLifecycleFormatterError):
                format_for_mediator(invalid)
        invalid = copy.deepcopy(result)
        invalid["unavailable_industries"][1] = invalid["unavailable_industries"][0]
        with self.assertRaises(BusinessLifecycleFormatterError):
            format_for_mediator(invalid)

    def test_all_unscored_cases_do_not_require_invented_counts(self):
        zero = [dict(row, similr_induty_stor_co=0, clsbiz_stor_co=0) for row in raw_rows()]
        excluded = [dict(raw_rows()[0], svc_induty_cd="CS300043")]
        for rows in (zero, excluded):
            with (
                self.subTest(rows=rows),
                patch(
                    "app.agents.business_lifecycle.preprocess.fetch_recent_store_data",
                    return_value=rows,
                ),
            ):
                result = build_agent_input("3120240", "20244", 4)
            self.assertEqual(result["industries"], [])
            self.assertEqual(
                len(result["unavailable_industries"]) + len(result["partial_industries"]), 75
            )
            self.assertEqual(len(result["partial_industries"]), 2 if rows == zero else 0)

    def test_partial_input_keeps_coverage_and_observed_metrics(self):
        rows = [r for r in raw_rows() if r["svc_induty_cd"] != "CS100005"]
        with patch(
            "app.agents.business_lifecycle.preprocess.fetch_recent_store_data", return_value=rows
        ):
            result = build_agent_input("3120240", "20244", 4)
        row = next(i for i in result["partial_industries"] if i["industry_id"] == "I210")
        self.assertEqual(row["data_status"], "incomplete")
        self.assertFalse(row["data_complete"])
        self.assertEqual(row["metrics"]["latest_store_count"], 90)
        self.assertEqual(row["source_coverage"]["observed_source_count"], 3)
        self.assertEqual(row["source_coverage"]["expected_source_count"], 4)


class LifecyclePartialDataTests(unittest.TestCase):
    def setUp(self):
        self.quarters = get_recent_quarters("20244", 12)

    def run_pipeline(self, rows):
        def request_page(**kwargs):
            page_rows = [
                {key.upper(): value for key, value in row.items()}
                for row in rows
                if row["stdr_yyqu_cd"] == kwargs["quarter"]
            ]
            if not page_rows:
                return {"RESULT": {"CODE": "INFO-200"}}
            return {
                "VwsmTrdarStorQq": {
                    "RESULT": {"CODE": "INFO-000"},
                    "list_total_count": len(page_rows),
                    "row": page_rows,
                }
            }

        async def completion(prompt, input_json, settings):
            industries = json.loads(input_json)["industries"]
            for item in industries:
                self.assertTrue(item["score_available"])
                self.assertTrue(item["data_complete"])
            # 모델이 품질 정보를 생략해도 Python 계산값을 복원해야 합니다.
            return {
                "industry_scores": [
                    {"industry_id": item["industry_id"], "type": "안정형"} for item in industries
                ]
            }

        with (
            patch("app.agents.business_lifecycle.client.request_page", side_effect=request_page),
            patch("app.agents.business_lifecycle.client.get_api_key", return_value="test-key"),
            patch("app.llm.client.complete_json", side_effect=completion) as llm,
        ):
            result = run_business_lifecycle_agent("3120240", "20244", 12, "partial-test")
        formatted = format_for_mediator(result)
        AgentAnalysis.model_validate(formatted.model_dump())
        json.dumps(formatted.model_dump(), allow_nan=False)
        if formatted.data:
            industries = formatted.data["industries"]
            self.assertEqual(len(industries), 75)
            self.assertEqual({i["industry_id"]: i["industry_name"] for i in industries}, INDUSTRIES)
            self.assertEqual(formatted.data["taxonomy"]["id"], "sbiz-middle-75")
        return result, formatted, llm.call_count

    def test_observed_quarter_threshold_and_complete_score_regression(self):
        for count in (0, 1, 2, 5, 6, 7, 8, 12):
            with self.subTest(count=count):
                observed = self.quarters[-count:] if count else []
                rows = [
                    row
                    for row in raw_rows(self.quarters)
                    if row["svc_induty_cd"] != "CS100001" or row["stdr_yyqu_cd"] in observed
                ]
                internal, result, _ = self.run_pipeline(rows)
                item = next(i for i in result.data["industries"] if i["industry_id"] == "I201")
                self.assertEqual(item["analysis_available"], count >= 2)
                self.assertEqual(item["data_available"], count > 0)
                self.assertEqual(item["data_complete"], count == 12)
                self.assertEqual(item["score_available"], count == 12)
                self.assertEqual(item["score"], 95 if count == 12 else None)
                self.assertEqual(item["source_coverage"]["observed_quarters"], count)
                self.assertEqual(item["source_coverage"]["complete_quarters"], count)
                self.assertEqual(item["source_coverage"]["observed_quarter_codes"], observed)
                self.assertEqual(item["metrics"]["avg_store_count"], 20 if count else None)
                group = (
                    "industry_scores"
                    if count == 12
                    else "partial_industries"
                    if count >= 2
                    else "unavailable_industries"
                )
                self.assertIn("I201", [i["industry_id"] for i in internal[group]])
                if 2 <= count < 12:
                    self.assertEqual(item["data_status"], "incomplete")
                    self.assertEqual(item["type"], "부분 관측")
                    self.assertIn("관측", item["warning"])
                    self.assertEqual(result.data["coverage"]["partial_industries"], 1)

    def test_only_partial_data_is_delivered_without_a_lifecycle_llm_call(self):
        for count in (1, 2, 5, 8):
            with self.subTest(count=count):
                rows = [
                    row
                    for row in raw_rows(self.quarters[-count:])
                    if row["svc_induty_cd"] == "CS100001"
                ]
                _, result, calls = self.run_pipeline(rows)
                self.assertEqual(calls, 0)
                self.assertEqual(result.status, "partial" if count >= 2 else "no_data")
                if count == 1:
                    self.assertEqual(result.data, {})
                else:
                    self.assertEqual(result.data["coverage"]["scored_industries"], 0)
                    self.assertEqual(result.data["coverage"]["available_industries"], 1)
                    self.assertTrue(any("점수 없이" in w for w in result.warnings))

    def test_no_supported_observations_remain_no_data(self):
        rows = [dict(raw_rows()[0], svc_induty_cd="CS300043")]
        internal, result, calls = self.run_pipeline(rows)
        self.assertEqual(calls, 0)
        self.assertEqual(result.status, "no_data")
        self.assertEqual(result.data, {})
        self.assertEqual(len(internal["unavailable_industries"]), 75)

    def test_appearing_disappearing_and_gapped_industries_keep_observed_changes(self):
        for observed in (
            self.quarters[7:],
            self.quarters[:5],
            self.quarters[3:8],
            [self.quarters[0], self.quarters[-1]],
        ):
            with self.subTest(observed=observed):
                rows = [
                    dict(row, opbiz_stor_co=3, clsbiz_stor_co=1)
                    for row in raw_rows(observed)
                    if row["svc_induty_cd"] == "CS100001"
                ]
                _, result, _ = self.run_pipeline(rows)
                item = next(i for i in result.data["industries"] if i["industry_id"] == "I201")
                metrics = item["metrics"]
                self.assertEqual(metrics["avg_store_count"], 20)
                self.assertEqual(metrics["period_open_count"], len(observed) * 3)
                self.assertEqual(metrics["period_close_count"], len(observed))
                self.assertEqual(metrics["period_net_change"], len(observed) * 2)
                self.assertEqual(metrics["net_change_rate"], 10)
                self.assertEqual(metrics["avg_close_rate"], 5)
                self.assertEqual(
                    metrics["latest_store_count"], 20 if self.quarters[-1] in observed else None
                )
                recent_count = len(set(observed) & set(self.quarters[-4:]))
                self.assertEqual(
                    metrics["recent_year_open_count"], recent_count * 3 if recent_count else None
                )
                self.assertEqual(item["source_coverage"]["observed_quarter_codes"], observed)
                self.assertIsNone(item["score"])

    def test_partial_sources_keep_counts_and_never_enter_relative_score_population(self):
        rows = [row for row in raw_rows(self.quarters) if row["svc_induty_cd"] != "CS100006"]
        _, result, _ = self.run_pipeline(rows)
        items = {i["industry_id"]: i for i in result.data["industries"]}
        item = items["I210"]
        self.assertTrue(item["analysis_available"])
        self.assertFalse(item["data_complete"])
        self.assertFalse(item["score_available"])
        self.assertEqual(item["data_status"], "incomplete")
        self.assertEqual(item["metrics"]["latest_store_count"], 70)
        self.assertEqual(item["metrics"]["period_close_count"], 120)
        self.assertEqual(item["metrics"]["avg_close_rate"], 14.29)
        coverage = item["source_coverage"]
        self.assertEqual(coverage["observed_quarters"], 12)
        self.assertEqual(coverage["complete_quarters"], 0)
        self.assertEqual(coverage["observed_source_count"], 3)
        self.assertEqual(coverage["expected_source_count"], 4)
        self.assertEqual(coverage["observed_source_rows"], 36)
        self.assertEqual(coverage["expected_source_rows"], 48)
        self.assertEqual(items["I201"]["score"], 100)

    def test_source_composition_and_null_fields_are_preserved(self):
        rows = [
            row
            for row in raw_rows(self.quarters)
            if row["svc_induty_cd"] != "CS100006" or row["stdr_yyqu_cd"] in self.quarters[:6]
        ]
        rows[0]["opbiz_stor_co"] = None
        _, result, _ = self.run_pipeline(rows)
        item = next(i for i in result.data["industries"] if i["industry_id"] == "I210")
        self.assertEqual(item["source_coverage"]["complete_quarters"], 5)
        self.assertEqual(item["source_coverage"]["observed_source_count"], 4)
        by_quarter = item["source_coverage"]["quarterly_source_ids"]
        self.assertEqual(len(by_quarter[self.quarters[0]]), 4)
        self.assertEqual(len(by_quarter[self.quarters[-1]]), 3)
        self.assertIsNone(item["metrics"]["period_open_count"])
        self.assertIsNone(item["metrics"]["net_change_rate"])
        self.assertEqual(item["metrics"]["period_close_count"], 120)
        self.assertIsNone(item["score"])

    def test_unsupported_industry_has_no_evidence(self):
        _, result, _ = self.run_pipeline(raw_rows(self.quarters))
        item = next(i for i in result.data["industries"] if i["industry_id"] == "I205")
        self.assertEqual(item["data_status"], "unsupported")
        self.assertFalse(item["analysis_available"])
        self.assertFalse(item["data_available"])
        self.assertIsNone(item["score"])
        self.assertEqual(item["source_coverage"]["observed_quarters"], 0)
        self.assertEqual(item["source_coverage"]["expected_source_count"], 0)
        self.assertEqual(item["type"], "판단 보류")

    def test_mediator_receives_and_can_cite_unscored_partial_metrics(self):
        rows = [
            dict(row, opbiz_stor_co=3, clsbiz_stor_co=1)
            for row in raw_rows(self.quarters[-2:])
            if row["svc_induty_cd"] == "CS100001"
        ]
        _, result, _ = self.run_pipeline(rows)
        index = next(
            n for n, item in enumerate(result.data["industries"]) if item["industry_id"] == "I201"
        )
        path = f"/industries/{index}/metrics/period_net_change"

        def generate(prompt, payload):
            self.assertIn("score_available=false", prompt)
            self.assertIn("2 미만", prompt)
            self.assertIn("누락을 0으로 채우거나", prompt)
            data = json.loads(payload)["analyses"][0]["data"]
            self.assertEqual(data, result.data)
            item = data["industries"][index]
            self.assertFalse(item["score_available"])
            self.assertEqual(item["metrics"]["period_net_change"], 4)
            return {
                "status": "ok",
                "summary": "관측된 개폐업 변화를 보조 근거로 판단했습니다.",
                "recommendations": [
                    {
                        "category": {"major": "음식점업", "middle": "한식 음식점업"},
                        "score": 55,
                        "reasons": ["관측 2분기의 개폐업 순증감은 4개입니다."],
                        "evidence": [{"agent_id": "business_lifecycle", "path": path}],
                        "risks": ["2분기 관측만으로 장기 안정성을 판단할 수 없습니다."],
                    }
                ],
                "not_recommended": [],
                "limitations": ["2분기 관측 자료만 활용했습니다."],
            }

        decision = asyncio.run(
            decide(
                DecisionRequest(
                    request_id=result.request_id, address="테스트 주소", analyses=[result]
                ),
                generate=generate,
            )
        )
        self.assertEqual(decision.status, "partial")
        self.assertEqual(decision.recommendations[0].evidence[0].path, path)
        self.assertEqual(decision.source_analyses[0].data, result.data)


class CommercialMasterTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_master_is_configuration_error(self):
        settings = Settings(upjong_master_path=Path("missing-test-master.csv"))
        result = await analyze(
            AnalysisTask(request_id="test", site=SITE),
            settings,
            FakeClient(settings, sample_stores()),
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "INDUSTRY_CONFIG_ERROR")
        self.assertEqual(result.data, {})

    async def test_unknown_middle_is_reported_without_expanding_master(self):
        settings = Settings()
        stores = sample_stores()
        stores.append(replace(stores[0], middle_code="UNKNOWN", store_id="unknown"))
        result = await analyze(
            AnalysisTask(request_id="test", site=SITE), settings, FakeClient(settings, stores)
        )
        self.assertEqual({r["code"] for r in result.data["by_middle"]}, set(INDUSTRIES))
        self.assertEqual(result.data["coverage"]["mapped_store_count"], 10)
        self.assertEqual(result.data["coverage"]["unmapped_store_count"], 1)

    def test_invalid_master_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "master.csv"
            for rows in ([], [MASTER[0], MASTER[0]]):
                write_master(path, rows)
                with self.subTest(rows=rows), self.assertRaises(ValueError):
                    load_middle_master(Settings(upjong_master_path=path))

    def test_short_csv_row_is_configuration_error(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "master.csv"
            path.write_text(
                "middle_code,middle_name,major_code,major_name\nI201,한식\n", encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                load_middle_master(Settings(upjong_master_path=path))

    def test_operational_master_rejects_incomplete_catalog(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "master.csv"
            write_master(path, MASTER)
            with (
                patch("app.agents.commercial_area.industries.MASTER_PATH", path),
                self.assertRaises(ValueError),
            ):
                load_middle_master(Settings(upjong_master_path=path))

    async def test_injected_small_master_is_not_labelled_canonical(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "master.csv"
            write_master(path, MASTER)
            settings = Settings(upjong_master_path=path)
            result = await analyze(
                AnalysisTask(request_id="test", site=SITE),
                settings,
                FakeClient(settings, sample_stores()),
            )
        self.assertEqual(result.data.get("taxonomy", {}).get("id"), "custom-middle")
