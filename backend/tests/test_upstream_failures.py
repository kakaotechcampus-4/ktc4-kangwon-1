"""외부 응답 오류가 공통 계약 오류로 번지지 않는지 검사합니다."""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import pandas as pd
from test_business_lifecycle_agent import fake_area, task
from test_industry_pipeline import preprocess, raw_rows

from app.agents.business_lifecycle import agent as lifecycle
from app.agents.business_lifecycle.config import Settings as LifecycleSettings
from app.agents.business_lifecycle.scoring import calculate_lifecycle_scores
from app.agents.commercial_area import agent as commercial
from app.agents.commercial_area.client import StoreClient
from app.agents.commercial_area.config import Settings as CommercialSettings
from app.agents.floating_population import agent as population
from app.agents.floating_population.client import SeoulOpenDataClient
from app.agents.floating_population.config import Settings as PopulationSettings
from app.agents.floating_population.models import FlpopRecord, PopulationRecord, TrdarArea
from app.agents.orchestration.workflow import run_agents
from app.mocks import mock_agents


class UpstreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_blank_area_names_do_not_discard_other_areas(self):
        rows = [
            {"TRDAR_CD": str(i), "TRDAR_CD_NM": name, "XCNTS_VALUE": 200000, "YDNTS_VALUE": 500000}
            for i, name in enumerate((None, "", "  ", "정상 상권"))
        ]
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={
                        "TbgisTrdarRelm": {
                            "row": rows,
                            "list_total_count": 4,
                            "RESULT": {"CODE": "INFO-000"},
                        }
                    },
                )
            )
        ) as http:
            areas = await SeoulOpenDataClient(
                PopulationSettings(api_key="test"), http=http
            ).fetch_trdar_areas()
        self.assertEqual([a.trdar_cd for a in areas], ["0", "1", "2", "3"])
        self.assertEqual([a.trdar_cd_nm for a in areas], ["", "", "", "정상 상권"])

    async def test_population_timeout_keeps_its_error_code(self):
        def timeout(request):
            raise httpx.ReadTimeout("시험", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as http:
            settings = PopulationSettings(api_key="test")
            result = await population.analyze(
                task(), settings=settings, client=SeoulOpenDataClient(settings, http=http)
            )
        self.assertEqual(result.error.code, "UPSTREAM_TIMEOUT")

    async def test_population_bad_payload_keeps_other_results(self):
        area = {"TRDAR_CD": "a", "XCNTS_VALUE": 200000, "YDNTS_VALUE": 500000}
        for payload in (
            "not-json",
            [],
            {"TbgisTrdarRelm": {"row": [{"TRDAR_CD": "a"}], "list_total_count": 1}},
            *(
                {"TbgisTrdarRelm": {"row": [area | bad], "list_total_count": 1}}
                for bad in (
                    {"TRDAR_CD": None},
                    {"TRDAR_CD": " "},
                    {"XCNTS_VALUE": "NaN"},
                    {"YDNTS_VALUE": "Infinity"},
                    {"RELM_AR": "-Infinity"},
                )
            ),
        ):
            with self.subTest(payload=payload):
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda _, payload=payload: (
                            httpx.Response(200, text=payload)
                            if isinstance(payload, str)
                            else httpx.Response(200, json=payload)
                        )
                    )
                ) as http:
                    settings = PopulationSettings(api_key="test")
                    client = SeoulOpenDataClient(settings, http=http)

                    async def analyze(value, settings=settings, client=client):
                        return await population.analyze(value, settings=settings, client=client)

                    agents = mock_agents() | {"floating_population": analyze}
                    results = await run_agents(task(), agents)
                result = next(r for r in results if r.agent_id == "floating_population")
                self.assertEqual(result.status, "error")
                self.assertEqual(result.error.code, "UPSTREAM_ERROR")
                self.assertEqual(sum(r.status == "ok" for r in results), 2)

    def test_population_rows_reject_missing_codes_and_nonfinite_counts(self):
        for kind in ("FLPOP", "REPOP", "WRC_POPLTN"):
            row = {"TRDAR_CD": "a", "STDR_YYQU_CD": "20262", f"TOT_{kind}_CO": 0}
            parse = (
                FlpopRecord.from_api_row
                if kind == "FLPOP"
                else lambda value, kind=kind: PopulationRecord.from_api_row(value, kind)
            )
            self.assertEqual(parse(row).total, 0)
            for bad in (
                {"TRDAR_CD": None},
                {"TRDAR_CD": ""},
                {"TRDAR_CD": " "},
                {f"TOT_{kind}_CO": "NaN"},
                {f"TOT_{kind}_CO": "Infinity"},
                {f"AGRDE_10_{kind}_CO": "-Infinity"},
            ):
                with self.subTest(kind=kind, bad=bad), self.assertRaises(ValueError):
                    parse(row | bad)

    def test_optional_area_labels_are_normalized(self):
        area = TrdarArea.from_api_row(
            {
                "TRDAR_CD": "a",
                "TRDAR_CD_NM": "상권",
                "XCNTS_VALUE": 200000,
                "YDNTS_VALUE": 500000,
                "TRDAR_SE_CD_NM": " ",
                "ADSTRD_CD_NM": "",
            }
        )
        self.assertIsNone(area.trdar_se_nm)
        self.assertIsNone(area.adstrd_nm)

    async def test_commercial_decode_and_redirect_errors_are_collected(self):
        for error in (httpx.DecodingError("bad"), httpx.TooManyRedirects("redirect")):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as folder:

                def broken(request, error=error):
                    raise error

                async with httpx.AsyncClient(transport=httpx.MockTransport(broken)) as http:
                    settings = CommercialSettings(
                        cache_dir=Path(folder), sbiz_service_key="test", max_retries=0
                    )
                    result = await commercial.analyze(task(), settings, StoreClient(settings, http))
                self.assertEqual(result.status, "error")

    async def test_service_keys_are_sent_over_https(self):
        with tempfile.TemporaryDirectory() as folder:

            def respond(request):
                self.assertEqual(request.url.scheme, "https")
                return httpx.Response(200, json={"body": {"items": [], "totalCount": 0}})

            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
                settings = CommercialSettings(cache_dir=Path(folder), sbiz_service_key="test")
                await StoreClient(settings, http).stores_in_radius(37.5, 127, 300)

    async def test_single_industry_observations_survive_without_score(self):
        rows = [r for r in raw_rows() if r["svc_induty_cd"] == "CS100001"]
        with patch(
            "app.agents.business_lifecycle.preprocess.fetch_recent_store_data", return_value=rows
        ):
            result = await lifecycle.analyze(
                task(),
                settings=LifecycleSettings(base_quarter_override="20244", quarter_count=4),
                area_resolver=fake_area,
            )
        self.assertEqual(result.status, "partial")
        row = next(i for i in result.data["industries"] if i["industry_id"] == "SV020")
        self.assertIsNone(row["score"])
        self.assertEqual(row["metrics"]["latest_store_count"], 20)
        self.assertEqual(row["confidence"], "low")
        self.assertNotIn("0개 업종을 비교", result.data["summary"])
        self.assertIn("보류", result.data["summary"])

    async def test_unwritable_cache_does_not_discard_successful_fetch(self):
        with tempfile.TemporaryDirectory() as folder:
            blocked = Path(folder) / "file"
            await asyncio.to_thread(blocked.write_text, "not a directory")
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(200, json={"body": {"items": [], "totalCount": 0}})
                )
            ) as http:
                settings = CommercialSettings(cache_dir=blocked, sbiz_service_key="test")
                stores, meta = await StoreClient(settings, http).stores_in_radius(37.5, 127, 300)
            self.assertEqual(stores, [])
            self.assertEqual(meta["total_count"], 0)

    async def test_bad_lifecycle_environment_is_configuration_error(self):
        with patch.dict(os.environ, {"BUSINESS_LIFECYCLE_QUARTER_COUNT": "bad"}):
            result = await lifecycle.analyze(task())
        self.assertEqual(result.error.code, "CONFIG_ERROR")

    async def test_bad_lifecycle_number_is_upstream_error(self):
        rows = raw_rows()
        rows[0]["clsbiz_stor_co"] = "bad"
        with patch(
            "app.agents.business_lifecycle.preprocess.fetch_recent_store_data", return_value=rows
        ):
            result = await lifecycle.analyze(
                task(),
                settings=LifecycleSettings(base_quarter_override="20244", quarter_count=4),
                area_resolver=fake_area,
            )
        self.assertEqual(result.error.code, "UPSTREAM_ERROR")

    async def test_empty_lifecycle_rows_are_explicit_no_data(self):
        with patch(
            "app.agents.business_lifecycle.preprocess.fetch_recent_store_data", return_value=[]
        ):
            result = await lifecycle.analyze(
                task(),
                settings=LifecycleSettings(base_quarter_override="20244", quarter_count=4),
                area_resolver=fake_area,
            )
        self.assertEqual(result.status, "no_data")

    async def test_one_scored_industry_has_no_relative_rank(self):
        frame = await preprocess([r for r in raw_rows() if r["svc_induty_cd"] == "CS100001"])
        scored = calculate_lifecycle_scores(frame, 4).set_index("service_id")
        self.assertTrue(pd.isna(scored.loc["SV020", "lifecycle_score"]))
        self.assertEqual(scored.loc["SV020", "confidence"], "low")
        self.assertEqual(scored.loc["SV020", "latest_store_count"], 20)
