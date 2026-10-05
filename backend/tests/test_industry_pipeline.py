"""원본 건수부터 공통 업종 출력까지의 계약을 검사합니다."""

import copy
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from test_commercial_area_agent import SITE, FakeClient, sample_stores

from app.agents.business_lifecycle.agent import run_business_lifecycle_agent
from app.agents.business_lifecycle.client import normalize_row
from app.agents.business_lifecycle.formatter import (
    BusinessLifecycleFormatterError,
    format_for_mediator,
)
from app.agents.business_lifecycle.input_builder import build_agent_input
from app.agents.business_lifecycle.preprocess import preprocess_business_lifecycle_data
from app.agents.business_lifecycle.scoring import calculate_lifecycle_scores
from app.agents.commercial_area.agent import analyze
from app.agents.commercial_area.config import Settings
from app.agents.commercial_area.industries import load_middle_master
from app.industries import lookup
from app.industries.catalog import INDUSTRIES
from app.schemas import AnalysisTask


def raw_rows():
    # SV024의 네 원천을 합치면 분기당 점포 100, 폐업 10: 비율 평균 25%가 아닌 10%.
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
        for quarter in ("20241", "20242", "20243", "20244")
        for code, stores, closed in (
            ("CS100005", 10, 10),
            ("CS100006", 30, 0),
            ("CS100007", 30, 0),
            ("CS100008", 30, 0),
            ("CS100001", 20, 0),
        )
    ]


async def preprocess(rows):
    with patch(
        "app.agents.business_lifecycle.preprocess.fetch_recent_store_data", return_value=rows
    ):
        return await preprocess_business_lifecycle_data("3120240", "20244", 4)


class IndustryPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_preprocessing_scoring_and_frame_conversion_do_not_block_loop(self):
        from app.agents.business_lifecycle import input_builder, scoring
        from app.agents.business_lifecycle import preprocess as prep

        loop_thread = threading.get_ident()
        seen = set()

        def outside_loop(name, function):
            def run(*args, **kwargs):
                self.assertNotEqual(threading.get_ident(), loop_thread, name)
                seen.add(name)
                return function(*args, **kwargs)

            return run

        with (
            patch.object(prep, "fetch_recent_store_data", return_value=raw_rows()),
            patch.object(prep, "_number", side_effect=outside_loop("전처리", prep._number)),
            patch.object(
                scoring,
                "calculate_lifecycle_scores",
                side_effect=outside_loop("점수", scoring.calculate_lifecycle_scores),
            ),
            patch.object(
                input_builder, "to_int", side_effect=outside_loop("변환", input_builder.to_int)
            ),
        ):
            result = await build_agent_input("3120240", "20244", 4)
        self.assertEqual(seen, {"전처리", "점수", "변환"})
        self.assertEqual(result["coverage"]["scored_industries"], 2)

    async def test_lookup_support_matches_mapping(self):
        self.assertTrue(lookup.get("SV020").has_seoul)
        self.assertFalse(lookup.get("SV046").has_seoul)

    async def test_raw_counts_are_combined_before_rates_and_scores(self):
        frame = await preprocess(raw_rows())
        self.assertEqual(set(frame.service_id), set(INDUSTRIES))
        row = frame.set_index("service_id").loc["SV024"]
        self.assertEqual(row.period_close_count, 40)
        self.assertEqual(row.latest_store_count, 100)
        self.assertEqual(row.avg_close_rate, 10)
        scored = calculate_lifecycle_scores(frame, 4).set_index("service_id")
        self.assertEqual(scored.loc["SV024", "lifecycle_score"], 55)
        self.assertEqual(scored.loc["SV020", "lifecycle_score"], 95)

    async def test_identical_duplicates_do_not_inflate_counts(self):
        rows = raw_rows()
        frame = await preprocess(rows + [copy.deepcopy(rows[0])])
        self.assertEqual(frame.period_close_count.sum(), 40)

    async def test_conflicting_duplicates_are_rejected(self):
        rows = raw_rows()
        duplicate = dict(rows[0], opbiz_stor_co=123)
        with self.assertRaisesRegex(ValueError, "중복"):
            await preprocess(rows + [duplicate])

    async def test_other_request_scope_and_unknown_codes_are_rejected(self):
        for change in (
            {"trdar_cd": "elsewhere"},
            {"stdr_yyqu_cd": "20234"},
            {"svc_induty_cd": "UNKNOWN"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                await preprocess([dict(raw_rows()[0], **change)])

    async def test_malformed_numbers_are_not_observed_zero(self):
        for bad in ("broken", "", float("inf"), -1, 1.5, True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                await preprocess([dict(raw_rows()[0], opbiz_stor_co=bad)])

    async def test_null_zero_missing_and_unsupported_remain_distinct(self):
        rows = raw_rows()
        for row in rows:
            if row["svc_induty_cd"] == "CS100001":
                row["similr_induty_stor_co"] = 0
            if row["svc_induty_cd"] == "CS100005":
                row["clsbiz_stor_co"] = None
        frame = (await preprocess(rows)).set_index("service_id")
        self.assertIn("SV020", frame.index)
        self.assertEqual(frame.loc["SV020", "latest_store_count"], 0)
        self.assertTrue(pd.isna(frame.loc["SV020", "avg_close_rate"]))
        self.assertTrue(pd.isna(frame.loc["SV024", "period_close_count"]))
        self.assertEqual(frame.loc["SV020", "data_status"], "observed")
        self.assertEqual(frame.loc["SV021", "data_status"], "missing")
        self.assertEqual(frame.loc["SV046", "data_status"], "unsupported")
        for code in ("SV046", "SV047", "SV048", "SV049", "SV050", "SV051"):
            self.assertEqual(frame.loc[code, "data_status"], "unsupported")
            self.assertTrue(pd.isna(frame.loc[code, "period_open_count"]))

    async def test_missing_source_or_quarter_cannot_claim_complete_score(self):
        for rows in (
            [r for r in raw_rows() if r["svc_induty_cd"] != "CS100005"],
            [r for r in raw_rows() if r["stdr_yyqu_cd"] != "20242"],
        ):
            frame = await preprocess(rows)
            self.assertIn("SV024", set(frame.service_id))
            row = frame.set_index("service_id").loc["SV024"]
            self.assertFalse(row.data_complete)
            score = calculate_lifecycle_scores(frame, 4).set_index("service_id")
            self.assertTrue(pd.isna(score.loc["SV024", "lifecycle_score"]))

    async def test_api_to_formatter_uses_canonical_service_codes_without_llm(self):
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

        with (
            patch(
                "app.agents.business_lifecycle.client.request_page",
                side_effect=request_page,
            ),
            patch("app.agents.business_lifecycle.client.get_api_key", return_value="test-key"),
            patch("app.llm.client.complete_json", side_effect=AssertionError("모델 호출 금지")),
        ):
            result = await run_business_lifecycle_agent("3120240", "20244", 4, "pipeline-test")
        formatted = format_for_mediator(result)
        self.assertEqual({i["industry_id"] for i in formatted.data["industries"]}, set(INDUSTRIES))
        self.assertEqual(formatted.data["taxonomy"]["id"], "service-industry-51")
        snack = next(i for i in formatted.data["industries"] if i["industry_id"] == "SV024")
        self.assertEqual(snack["metrics"]["avg_close_rate"], 10)
        self.assertEqual(snack["score"], 55)
        # 40 / 400 = 10%는 분기 평균이며, 40 / 100 = 40%인 연간 비율이 아닙니다.
        self.assertEqual(snack["metrics"]["recent_year_close_rate"], 10)
        basis = formatted.data["scoring_method"].get("rate_basis", {})
        self.assertEqual(basis.get("unit"), "%/분기")
        self.assertEqual(basis.get("denominator"), "대상 분기의 점포 수 합계")
        self.assertEqual(basis.get("annualized"), False)
        self.assertFalse(any("검수" in warning for warning in formatted.warnings))
        for change in ({"industry_name": "잘못된 이름"}, {"industry_id": 1}, {"industry_id": True}):
            invalid = copy.deepcopy(result)
            invalid["industry_scores"][0].update(change)
            with self.subTest(change=change), self.assertRaises(BusinessLifecycleFormatterError):
                format_for_mediator(invalid)
        invalid = copy.deepcopy(result)
        invalid["unavailable_industries"][1] = invalid["unavailable_industries"][0]
        with self.assertRaises(BusinessLifecycleFormatterError):
            format_for_mediator(invalid)

    async def test_all_unscored_cases_do_not_require_invented_counts(self):
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
                result = await build_agent_input("3120240", "20244", 4)
            self.assertEqual(result["industries"], [])
            self.assertEqual(len(result["unavailable_industries"]), 51)

    async def test_unavailable_input_keeps_coverage_and_observed_metrics(self):
        rows = [r for r in raw_rows() if r["svc_induty_cd"] != "CS100005"]
        with patch(
            "app.agents.business_lifecycle.preprocess.fetch_recent_store_data", return_value=rows
        ):
            result = await build_agent_input("3120240", "20244", 4)
        unavailable = {i["industry_id"]: i for i in result["unavailable_industries"]}
        self.assertIn("SV024", unavailable)
        row = unavailable["SV024"]
        self.assertEqual(row["data_status"], "incomplete")
        self.assertFalse(row["data_complete"])
        self.assertIsNone(row["metrics"]["latest_store_count"])


class CommercialMasterTests(unittest.IsolatedAsyncioTestCase):
    async def test_operational_master_uses_catalog_without_reading_csv(self):
        with patch.object(Path, "open", side_effect=AssertionError("중복 CSV 읽기")):
            rows = load_middle_master(Settings())
        self.assertEqual({row.code for row in rows}, set(INDUSTRIES))

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
