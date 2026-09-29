"""상위에서 정한 설정이 요청 사이에 섞이지 않는지 검증합니다."""

import asyncio
import json
import os
import unittest
from unittest.mock import patch

import httpx

from app.agents.orchestration.workflow import build_react_agents, run_agents
from app.schemas import AGENT_IDS, AgentAnalysis, AnalysisTask, Scope, Site


class ExecutionSettingsTests(unittest.IsolatedAsyncioTestCase):
    def test_unused_analysis_model_options_do_not_block_execution_settings(self):
        from app.services.settings import ExecutionSettings

        with patch.dict(
            os.environ,
            {
                "FLOATING_POPULATION_LLM_TIMEOUT_SECONDS": "unused",
                "BUSINESS_LIFECYCLE_LLM_MAX_TOKENS": "unused",
                "COMMERCIAL_AREA_LLM_TIMEOUT_SECONDS": "unused",
                "ORCHESTRATION_LLM_TIMEOUT_SECONDS": "unused",
            },
            clear=True,
        ):
            settings = ExecutionSettings.from_env()
        self.assertEqual(settings.agent_timeout, 180)

    async def test_lifecycle_api_snapshot_reaches_probe_and_quarter_requests(self):
        from test_business_lifecycle_agent import task
        from test_industry_pipeline import raw_rows

        from app.services.settings import ExecutionSettings

        async def completion(prompt, input_json, settings):
            payload = json.loads(input_json)
            return {
                "industry_scores": [
                    dict(item, type="안정형", evidence=[], warning=None)
                    for item in payload["industries"]
                ]
            }

        httpx_client = httpx.AsyncClient
        for base_quarter in ("20244", ""):
            seen = []

            def respond(request, *, seen=seen):
                parts = str(request.url).rstrip("/").split("/")
                seen.append((parts[3], request.extensions["timeout"]["read"]))
                rows = [
                    {key.upper(): value for key, value in row.items()}
                    for row in raw_rows()
                    if row["stdr_yyqu_cd"] == "20241"
                ]
                for row in rows:
                    row["STDR_YYQU_CD"] = parts[-2]
                return httpx.Response(
                    200,
                    json=(
                        {
                            "VwsmTrdarStorQq": {
                                "RESULT": {"CODE": "INFO-000"},
                                "list_total_count": len(rows),
                                "row": rows,
                            }
                        }
                    ),
                )

            with patch.dict(
                os.environ,
                {
                    "BUSINESS_LIFECYCLE_API_KEY": "captured-key",
                    "BUSINESS_LIFECYCLE_TIMEOUT_SECONDS": "0.25",
                    "BUSINESS_LIFECYCLE_QUARTER_COUNT": "4",
                    "BUSINESS_LIFECYCLE_AREA_CODE": "3120240",
                    "BUSINESS_LIFECYCLE_AREA_NAME": "시험 상권",
                    "BUSINESS_LIFECYCLE_BASE_QUARTER": base_quarter,
                },
                clear=True,
            ):
                registry = build_react_agents(ExecutionSettings.from_env())
                os.environ["BUSINESS_LIFECYCLE_API_KEY"] = "later-env-key"
                os.environ["BUSINESS_LIFECYCLE_TIMEOUT_SECONDS"] = "0.75"
                with (
                    patch(
                        "httpx.AsyncClient",
                        side_effect=lambda **kw: httpx_client(
                            transport=httpx.MockTransport(respond), **kw
                        ),
                    ),
                    patch("app.llm.client.complete_json", side_effect=completion),
                ):
                    result = await registry["business_lifecycle"](task())
            self.assertEqual(result.status, "partial")
            self.assertEqual(seen, [("captured-key", 0.25)] * 4)

    async def test_parallel_registries_keep_per_agent_settings(self):
        from app.services.settings import ExecutionSettings

        seen = []

        def fake(agent_id):
            async def analyze(task, **kwargs):
                await asyncio.sleep(0)
                if agent_id == "commercial_area":
                    model = kwargs["settings"].sbiz_service_key
                elif agent_id == "floating_population":
                    self.assertNotIn("select", kwargs)
                    model = None
                else:
                    self.assertNotIn("llm_settings", kwargs)
                    model = None
                seen.append((task.request_id, agent_id, model))
                return AgentAnalysis(
                    request_id=task.request_id,
                    agent_id=agent_id,
                    status="no_data",
                    scope=Scope(area="시험", period="시험"),
                )

            return analyze

        with (
            patch("app.agents.floating_population.analyze", new=fake("floating_population")),
            patch("app.agents.business_lifecycle.analyze", new=fake("business_lifecycle")),
            patch("app.agents.commercial_area.analyze", new=fake("commercial_area")),
        ):
            registries = []
            for request in ("first", "second"):
                with patch.dict(
                    os.environ,
                    {"COMMERCIAL_AREA_API_KEY": f"{request}-commercial_area"},
                    clear=True,
                ):
                    registries.append(build_react_agents(ExecutionSettings.from_env()))
            with patch.dict(os.environ, {"ELICE_MODEL": "must-not-leak"}, clear=True):
                await asyncio.gather(
                    *(
                        run_agents(
                            AnalysisTask(
                                request_id=request,
                                site=Site(
                                    input_address="시험",
                                    road_address="시험",
                                    latitude=37.5,
                                    longitude=127.1,
                                ),
                            ),
                            registry,
                        )
                        for request, registry in zip(("first", "second"), registries, strict=True)
                    )
                )
        self.assertEqual(
            set(seen),
            {
                (request, name, f"{request}-{name}" if name == "commercial_area" else None)
                for request in ("first", "second")
                for name in AGENT_IDS
            },
        )

    def test_default_registry_uses_all_three_and_legacy_commercial_settings(self):
        from app.agents.commercial_area.config import Settings
        from app.services.settings import ExecutionSettings

        registry = build_react_agents(ExecutionSettings(commercial=Settings(analysis_radius_m=200)))
        self.assertEqual(set(registry), set(AGENT_IDS))

    def test_shape_path_uses_captured_settings_without_opening_real_files(self):
        from pathlib import Path

        from test_business_lifecycle_agent import GARAK_SITE

        from app.agents.business_lifecycle.area_resolver import (
            BusinessAreaNoDataError,
            resolve_area,
        )
        from app.agents.business_lifecycle.config import Settings

        with patch.dict(os.environ, {"BUSINESS_LIFECYCLE_AREA_SHP_PATH": "captured.shp"}):
            settings = Settings.from_env()
            os.environ["BUSINESS_LIFECYCLE_AREA_SHP_PATH"] = "later.shp"
            with patch(
                "app.agents.business_lifecycle.area_resolver.load_shape_features", return_value=[]
            ) as load:
                with self.assertRaises(BusinessAreaNoDataError):
                    resolve_area(GARAK_SITE, settings)
                load.assert_called_once_with(Path("captured.shp"))
