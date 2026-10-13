"""인구 결측의 파싱·파생 지표·JSON null 보존을 검사합니다."""

import json
import unittest
from unittest.mock import patch

from test_floating_population_population import QUARTER, _flpop, _pop

from app.agents.floating_population.agent import analyze
from app.agents.floating_population.classify import classify
from app.agents.floating_population.metrics import _aggregate, _benchmark, _trend
from app.agents.floating_population.models import FlpopRecord, PopulationRecord, TrdarArea, _num
from app.agents.floating_population.population import resident_block, summary_block
from app.geo import to_epsg5181
from app.mocks import mock_site
from app.schemas import AnalysisTask


class PopulationMissingnessTests(unittest.TestCase):
    def test_blank_and_null_tokens_become_none_but_zero_stays_numeric(self):
        for value in (None, "", " ", "null", " NULL "):
            with self.subTest(value=value):
                self.assertIsNone(_num({"value": value}, "value"))
        for value in (0, "0", "0.0"):
            self.assertEqual(_num({"value": value}, "value"), 0.0)
        with self.assertRaises(ValueError):
            _num({"value": "not-a-number"}, "value")

    def test_api_row_serializes_null_as_json_value(self):
        record = FlpopRecord.from_api_row(
            {"TRDAR_CD": "a", "STDR_YYQU_CD": QUARTER, "TOT_FLPOP_CO": 91}
        )
        data = json.loads(record.model_dump_json())
        self.assertEqual(data["total"], 91)
        self.assertIsNone(data["female"])
        self.assertIsNone(data["by_age"]["30"])
        self.assertNotIn('"null"', record.model_dump_json())
        population = PopulationRecord.from_api_row(
            {"TRDAR_CD": "a", "STDR_YYQU_CD": QUARTER, "TOT_REPOP_CO": "null"}, "REPOP"
        )
        self.assertIsNone(json.loads(population.model_dump_json())["total"])

    def test_partial_age_keeps_total_and_other_age_but_abstains_from_type(self):
        record = _flpop("a", 100)
        record.by_age["30"] = None
        pop = _aggregate([record], QUARTER)
        self.assertEqual(pop.daily_avg, 100)
        self.assertIsNone(pop.by_age["30"])
        self.assertIsNone(pop.age_share["30"])
        self.assertIsNotNone(pop.age_share["20"])
        result = classify(age_share=pop.age_share, weekend_to_weekday=pop.weekend_to_weekday_ratio)
        self.assertEqual(result.label, "판단 불가")
        self.assertIsNone(result.signals["age_30_40"])
        self.assertIsNone(_benchmark(pop, record.total, 1, 91).age_index["30"])

    def test_incomplete_sum_and_time_denominator_are_not_partial_totals(self):
        first, second = _flpop("a", 100), _flpop("b", 200)
        first.total = None
        first.by_time["00_06"] = None
        pop = _aggregate([first, second], QUARTER)
        self.assertIsNone(pop.daily_avg)
        self.assertIsNotNone(pop.by_age["20"])
        self.assertTrue(all(v is None for v in pop.time_per_hour_share.values()))
        self.assertIsNone(pop.peak_time_band)
        trend = _trend([("20261", [second]), (QUARTER, [first, second])], {"a", "b"})
        self.assertIsNone(trend.quarters[-1].daily_avg)
        self.assertIsNone(trend.qoq_change)
        self.assertEqual(trend.direction, "판단 불가")

    def test_actual_zero_remains_zero(self):
        pop = _aggregate([_flpop("a", 0)], QUARTER)
        self.assertEqual(pop.daily_avg, 0)
        self.assertEqual(pop.female_ratio, 0)
        self.assertEqual(pop.age_share["30"], 0)

    def test_resident_keeps_known_count_when_households_or_age_missing(self):
        record = _pop("a", 100, households=None)
        record.by_age["20"] = None
        block = resident_block([record], QUARTER, {"a"})
        self.assertEqual(block.count, 100)
        self.assertIsNone(block.households)
        self.assertIsNone(block.persons_per_household)
        self.assertIsNone(block.age_share["20"])
        self.assertIsNotNone(block.age_share["30"])
        missing_total = record.model_copy(update={"total": None})
        summary = summary_block([_flpop("a", 10)], 91, [missing_total], [_pop("a", 200)], {"a"})
        self.assertIsNone(summary.worker_to_resident_ratio)
        self.assertEqual(summary.composition, "판단 불가")


class MissingnessAgentTests(unittest.IsolatedAsyncioTestCase):
    async def run_agent(self, record):
        task = AnalysisTask(request_id="missingness", site=mock_site())
        x, y = to_epsg5181(task.site.latitude, task.site.longitude)

        class Client:
            async def fetch_trdar_areas(self):
                return [TrdarArea(trdar_cd="a", trdar_cd_nm="test", x=x, y=y, relm_ar=100)]

            async def fetch_flpop_series(self, codes, quarters):
                return [(QUARTER, [record])]

        with patch(
            "app.agents.floating_population.agent._load",
            return_value=[_pop("a", 100, households=50)],
        ):
            return await analyze(task, client=Client())

    async def test_partial_results_keep_null_and_valid_values_without_format_errors(self):
        record = _flpop("a", 100)
        record.by_age["30"] = None
        record.by_time["00_06"] = None
        record.female = None
        result = await self.run_agent(record)
        self.assertEqual(result.status, "partial")
        data = json.loads(result.model_dump_json())["data"]
        self.assertEqual(data["population"]["daily_avg"], 100)
        self.assertIsNone(data["population"]["female_ratio"])
        self.assertIsNone(data["population"]["by_age"]["30"])
        self.assertEqual(data["type"]["label"], "판단 불가")
        self.assertTrue(any("결측" in warning for warning in result.warnings))
        self.assertNotIn('"null"', result.model_dump_json())

    async def test_completely_missing_numeric_data_is_no_data(self):
        result = await self.run_agent(
            FlpopRecord.from_api_row({"TRDAR_CD": "a", "STDR_YYQU_CD": QUARTER})
        )
        self.assertEqual(result.status, "no_data")
