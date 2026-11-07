"""자료 없음과 실제 0, 미적용을 채점·보고서 인용에서 구분하는 회귀 사례입니다."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.application.facts import register_fact
from app.application.report import validate_proposal
from app.domain import scoring
from app.domain.baselines.floating_population import DAILY_TOTAL_PERCENTILES
from app.domain.report import ReportInvalid
from app.infrastructure.persistence.connection import connect, initialize
from app.infrastructure.persistence.raw_capture import capture_scope
from app.infrastructure.persistence.repository import create_request
from tests.fact_fixture import fact_record


class MissingDataTests(unittest.TestCase):
    def test_non_applicable_demand_has_different_guidance_from_missing_observations(self):
        items = {name: scoring.result(name, 3) for name in scoring.WEIGHTS}
        for name in ("D1", "D3"):
            items[name] = scoring.result(name, status="n.a.")
        report = scoring.summarize("G202", items, "해당 없음")
        self.assertIn(
            "시간대·연령 항목 미적용: 업종별 수요 별도 확인 필요", report["confirmation_conditions"]
        )
        self.assertNotIn("손님 수요 근거 없음", report["confirmation_conditions"])
        self.assertEqual(report["badge"], "조건부")
        self.assertEqual(report["lower"], 60)

        for name in ("D1", "D3"):
            with self.subTest(missing=name):
                mixed = {**items, name: scoring.result(name)}
                report = scoring.summarize("G202", mixed, "해당 없음")
                self.assertIn(
                    "적용 가능한 시간대·연령 수요 자료 미확인", report["confirmation_conditions"]
                )
                self.assertFalse(
                    any("항목 미적용" in text for text in report["confirmation_conditions"])
                )

    def test_zero_trend_is_observed_but_missing_trend_is_unknown(self):
        zero = scoring.score_item(
            "D4", {}, "G204", {"floating_population": {"trend": {"yoy_change": 0}}}
        )
        missing = scoring.score_item("D4", {}, "G204", {})
        self.assertEqual((zero["status"], zero["value"]), ("observed", 0))
        self.assertEqual((missing["status"], missing["points"]), ("unknown", None))

    def test_zero_stores_require_complete_collection_and_an_explicit_industry_row(self):
        sample = {
            "commercial_collection_complete": True,
            "commercial_area": {
                "radius_m": 500,
                "by_middle": [{"code": "G204", "density_per_km2": 0}],
            },
            "floating_population": {
                "benchmark": {"mean_daily_per_trade_area": DAILY_TOTAL_PERCENTILES[50]}
            },
        }
        self.assertEqual(scoring.score_item("C1", {}, "G204", sample)["status"], "observed")
        sample["commercial_area"]["by_middle"] = []
        self.assertEqual(scoring.score_item("C1", {}, "G204", sample)["status"], "unknown")
        sample["commercial_area"]["by_middle"] = [{"code": "G204", "density_per_km2": 0}]
        sample["commercial_collection_complete"] = False
        self.assertEqual(scoring.score_item("C1", {}, "G204", sample)["status"], "unknown")

    def test_no_facility_search_results_do_not_prove_absence(self):
        profile = {"required_facilities": "HP8", "max_distance_m": "500"}
        sample = {
            "facilities": {
                "data": {
                    "queries": {
                        "q": {"request": {"facility_code": "HP8"}, "status": "ok", "place_ids": []}
                    },
                    "places": {},
                }
            }
        }
        scored = scoring.score_item("C4", profile, "G215", sample)
        self.assertEqual((scored["status"], scored["points"]), ("unknown", None))

    def test_non_applicable_facility_is_not_an_unavailable_measurement(self):
        scored = scoring.score_item("C4", {}, "I201", {"runtime_partial_sources": ["map"]})
        self.assertEqual((scored["status"], scored["points"]), ("n.a.", None))

    def test_zero_closures_are_not_replaced_by_missing_data(self):
        sample = {
            "business_lifecycle": {
                "metadata": {
                    "base_quarter": scoring.BASELINE_BASE_QUARTER,
                    "quarter_count": scoring.BASELINE_QUARTER_COUNT,
                },
                "industries": [
                    {
                        "industry_id": "I201",
                        "data_complete": True,
                        "metrics": {"avg_store_count": 40, "recent_year_close_rate": 0},
                    }
                ],
            }
        }
        with patch.object(
            scoring, "SEOUL_INDUSTRY_LIFECYCLE_BASELINE", {"I201": {"recent_year_close_rate": 0.1}}
        ):
            scored = scoring.score_item("S1", {}, "I201", sample)
            self.assertEqual((scored["status"], scored["grade"]), ("observed", 4))
            sample["business_lifecycle"]["industries"][0]["data_complete"] = False
            self.assertEqual(scoring.score_item("S1", {}, "I201", sample)["status"], "unknown")

    def test_population_substitution_is_explicit(self):
        profile = {"target_population": "상주", "target_age_bands": "20"}
        sample = {"floating_population": {"resident": {}, "population": {"age_share": {"20": 0.1}}}}
        with patch.object(scoring.population_baseline, "AGE_SHARE_AVG", {"20": 0.1}):
            scored = scoring.score_item("D3", profile, "G204", sample)
        self.assertEqual(scored["value"]["population"], "유동")
        self.assertEqual(scored["value"]["requested_population"], "상주")
        self.assertEqual(scored["reason"], "유동 연령 대체")

    def proposal(self, segment):
        return SimpleNamespace(
            summary_segments=[segment],
            limitations_segments=[],
            candidates=[],
            excluded_candidates=[],
        )

    def test_unknown_or_uncitable_facts_cannot_support_report_claims(self):
        proposal = self.proposal(SimpleNamespace(type="fact", fact_id="f"))
        for status, citable in (("unknown", False), ("observed", False)):
            with (
                self.subTest(status=status),
                patch(
                    "app.application.report.fact_rows",
                    return_value={"f": fact_record("f", status=status, citable=citable)},
                ),
            ):
                with self.assertRaisesRegex(ReportInvalid, "미확인 fact"):
                    validate_proposal(None, proposal)

    def test_numbers_without_fact_slots_are_rejected(self):
        proposal = self.proposal(SimpleNamespace(type="text", text="유동인구가 100명입니다."))
        with self.assertRaisesRegex(ReportInvalid, "fact 슬롯"):
            validate_proposal(None, proposal)


class FactValueTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = initialize(Path(self.temp.name) / "facts.sqlite3")
        create_request("fact-values", "서울 테스트", db_path=self.path)

    def tearDown(self):
        self.temp.cleanup()

    async def fact_arguments(self, scope):
        await scope.record(
            source="commercial_area",
            source_type="api",
            args={},
            page="1",
            status=200,
            payload={"rows": [{"bizesId": "zero", "indsMclsCd": "I201", "store_count": 0}]},
        )
        with connect(self.path) as db:
            ref = db.execute("SELECT raw_row_id FROM raw_rows").fetchone()[0]
        return {
            "industry_code": "I201",
            "source": "commercial_area",
            "metric": "store_count",
            "unit": "개",
            "row_ids": [ref],
        }

    async def test_missing_value_cannot_be_registered_as_observed(self):
        async with capture_scope("fact-values", self.path) as scope:
            arguments = await self.fact_arguments(scope)
            with self.assertRaisesRegex(ValueError, "실제 값"):
                await asyncio.to_thread(
                    register_fact, scope, **arguments, value=None, status="observed"
                )

    async def test_observed_zero_and_unknown_zero_remain_distinct(self):
        async with capture_scope("fact-values", self.path) as scope:
            arguments = await self.fact_arguments(scope)
            observed = await asyncio.to_thread(
                register_fact, scope, **arguments, value=0, status="observed"
            )
            unknown = await asyncio.to_thread(
                register_fact, scope, **arguments, value=0, status="unknown"
            )
        with connect(self.path) as db:
            values = {
                row[0]: (json.loads(row[1]), row[2], bool(row[3]))
                for row in db.execute("SELECT fact_id,value_json,status,citable FROM facts")
            }
        self.assertEqual(values[observed], (0, "observed", True))
        self.assertEqual(values[unknown], (None, "unknown", False))


if __name__ == "__main__":
    unittest.main()
