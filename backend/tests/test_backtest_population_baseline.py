import asyncio
import unittest

from app.agents.floating_population import baseline, classify
from app.agents.floating_population.metrics import _aggregate
from app.agents.floating_population.models import AGE_BANDS, TIME_BANDS, FlpopRecord
from backtest.population_baseline import aggregate, as_of, load, measure

QUARTER = "20234"
AGE_KEYS = {
    "10": "AGRDE_10_FLPOP_CO",
    "20": "AGRDE_20_FLPOP_CO",
    "30": "AGRDE_30_FLPOP_CO",
    "40": "AGRDE_40_FLPOP_CO",
    "50": "AGRDE_50_FLPOP_CO",
    "60": "AGRDE_60_ABOVE_FLPOP_CO",
}
DAY_KEYS = ["MON", "TUES", "WED", "THUR", "FRI", "SAT", "SUN"]


def api_row(code, ages, times, days, quarter=QUARTER):
    total = sum(ages)
    row = {
        "STDR_YYQU_CD": quarter,
        "TRDAR_CD": code,
        "TOT_FLPOP_CO": total,
        "ML_FLPOP_CO": total / 2,
        "FML_FLPOP_CO": total / 2,
    }
    row.update({AGE_KEYS[a]: v for a, v in zip(AGE_BANDS, ages, strict=True)})
    row.update({f"TMZON_{b}_FLPOP_CO": v for b, v in zip(TIME_BANDS, times, strict=True)})
    row.update({f"{d}_FLPOP_CO": v for d, v in zip(DAY_KEYS, days, strict=True)})
    return row


ROWS = [
    api_row("A", [10, 20, 30, 40, 50, 60], [60, 50, 30, 30, 20, 20], [30, 30, 30, 30, 30, 30, 30]),
    api_row(
        "B",
        [600, 500, 400, 300, 200, 100],
        [300, 300, 300, 300, 600, 300],
        [200, 200, 200, 200, 200, 600, 500],
    ),
]


def records(rows):
    return [FlpopRecord.from_api_row(r) for r in rows]


class FakeClient:
    def __init__(self, rows):
        self.rows, self.extras = rows, []
        self.settings = type("S", (), {"flpop_service": "SVC", "flpop_max_pages": 5})()

    async def _fetch_all(self, service, max_pages, extra=None):
        self.extras.append((service, max_pages, extra))
        return self.rows


class AggregateTests(unittest.TestCase):
    def test_shares_match_the_agent_definitions(self):
        result = aggregate(records(ROWS), QUARTER)
        agent = _aggregate(records(ROWS), QUARTER)
        self.assertEqual(result["AGE_SHARE_AVG"], agent.age_share)
        self.assertEqual(result["TIME_PER_HOUR_SHARE_AVG"], agent.time_per_hour_share)
        self.assertEqual(result["WEEKEND_TO_WEEKDAY_AVG"], agent.weekend_to_weekday_ratio)
        self.assertEqual(result["quarter"], QUARTER)
        self.assertEqual(result["area_count"], 2)
        self.assertEqual(result["total"], 2310)

    def test_seoul_average_is_weighted_and_grouped(self):
        result = aggregate(records(ROWS), QUARTER)
        weekday = (30 * 5 + 200 * 5) / 5
        weekend = (30 + 30 + 600 + 500) / 2
        self.assertEqual(
            result["SEOUL_AVG"],
            {
                "age_10": round(610 / 2310, 3),
                "age_20": round(520 / 2310, 3),
                "age_30_40": round(770 / 2310, 3),
                "age_50_60": round(410 / 2310, 3),
                "weekend_to_weekday": round(weekend / weekday, 3),
            },
        )

    def test_scale_percentiles_use_per_area_totals(self):
        rows = [
            api_row(str(i), [t, 0, 0, 0, 0, 0], [t, 0, 0, 0, 0, 0], [t, 0, 0, 0, 0, 0, 0])
            for i, t in enumerate([300, 100, 500, 200, 400])
        ]
        scale = aggregate(records(rows), QUARTER)["SCALE_PERCENTILES"]
        self.assertEqual(list(scale), [str(p) for p in range(5, 100, 5)])
        self.assertEqual(scale["5"], 100.0)
        self.assertEqual(scale["15"], 200.0)
        self.assertEqual(scale["50"], 300.0)
        self.assertEqual(scale["95"], 500.0)

    def test_missing_values_are_refused(self):
        row = dict(ROWS[0])
        row["AGRDE_10_FLPOP_CO"] = None
        with self.assertRaises(ValueError):
            aggregate(records([row, ROWS[1]]), QUARTER)


class MeasureTests(unittest.TestCase):
    def test_measure_reads_only_the_requested_quarter(self):
        client = FakeClient(ROWS)
        result = asyncio.run(measure(QUARTER, client))
        self.assertEqual(client.extras, [("SVC", 5, QUARTER)])
        self.assertEqual(result, aggregate(records(ROWS), QUARTER))

    def test_rows_from_another_quarter_are_refused(self):
        rows = [ROWS[0], {**ROWS[1], "STDR_YYQU_CD": "20262"}]
        with self.assertRaises(ValueError):
            asyncio.run(measure(QUARTER, FakeClient(rows)))

    def test_empty_quarter_is_refused(self):
        with self.assertRaises(ValueError):
            asyncio.run(measure(QUARTER, FakeClient([])))


class LoadAndPatchTests(unittest.TestCase):
    def test_shipped_file_is_for_the_backtest_quarter(self):
        values = load("20234")
        self.assertEqual(values["quarter"], "20234")
        self.assertGreater(values["area_count"], 1000)

    def test_missing_quarter_names_the_quarter(self):
        with self.assertRaises(FileNotFoundError) as caught:
            load("19991")
        self.assertIn("19991", str(caught.exception))

    def test_as_of_patches_and_restores_every_constant(self):
        values = aggregate(records(ROWS), QUARTER)
        values["SCALE_PERCENTILES"] = {str(p): float(p * 10) for p in range(5, 100, 5)}
        before = (
            baseline.BASELINE_LABEL,
            baseline.AGE_SHARE_AVG,
            baseline.TIME_PER_HOUR_SHARE_AVG,
            baseline.WEEKEND_TO_WEEKDAY_AVG,
            baseline.SCALE_PERCENTILES,
            classify.SEOUL_AVG,
            classify.STUDENT_MIN,
            classify.LEISURE_MIN,
            classify.OFFICE_MIN,
            classify.RESIDENT_MIN,
        )
        with as_of(values):
            self.assertEqual(baseline.BASELINE_LABEL, "서울 전체 상권 평균 (2023년 4분기 · 2곳)")
            self.assertEqual(baseline.AGE_SHARE_AVG, values["AGE_SHARE_AVG"])
            self.assertEqual(baseline.TIME_PER_HOUR_SHARE_AVG, values["TIME_PER_HOUR_SHARE_AVG"])
            self.assertEqual(baseline.WEEKEND_TO_WEEKDAY_AVG, values["WEEKEND_TO_WEEKDAY_AVG"])
            self.assertEqual(baseline.SCALE_PERCENTILES[5], values["SCALE_PERCENTILES"]["5"])
            self.assertEqual(classify.SEOUL_AVG, values["SEOUL_AVG"])
            seoul = values["SEOUL_AVG"]
            self.assertEqual(classify.STUDENT_MIN, seoul["age_10"] + classify.MARGIN)
            self.assertEqual(classify.LEISURE_MIN, seoul["age_20"] + classify.MARGIN)
            self.assertEqual(classify.OFFICE_MIN, seoul["age_30_40"] + classify.MARGIN)
            self.assertEqual(classify.RESIDENT_MIN, seoul["age_50_60"] + classify.MARGIN)
            result = classify.classify(
                age_share={a: 0.0 for a in AGE_BANDS}, weekend_to_weekday=1.0
            )
            self.assertEqual(
                result.thresholds["age_10_min"], round(seoul["age_10"] + classify.MARGIN, 4)
            )
            self.assertEqual(baseline.scale_percentile(500.0), 50)
            self.assertEqual(baseline.scale_percentile(740.0), 74)
        after = (
            baseline.BASELINE_LABEL,
            baseline.AGE_SHARE_AVG,
            baseline.TIME_PER_HOUR_SHARE_AVG,
            baseline.WEEKEND_TO_WEEKDAY_AVG,
            baseline.SCALE_PERCENTILES,
            classify.SEOUL_AVG,
            classify.STUDENT_MIN,
            classify.LEISURE_MIN,
            classify.OFFICE_MIN,
            classify.RESIDENT_MIN,
        )
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
