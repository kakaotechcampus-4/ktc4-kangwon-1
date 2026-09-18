"""상위에서 정한 설정이 요청 사이에 섞이지 않는지 검증합니다."""

import asyncio
import io
import json
import os
import unittest
from unittest.mock import patch

from app.agents.orchestration.workflow import build_react_agents, default_agents, run_agents
from app.schemas import AGENT_IDS, AgentAnalysis, AnalysisTask, Scope, Site


class ExecutionSettingsTests(unittest.IsolatedAsyncioTestCase):
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

        for base_quarter in ("20244", ""):
            seen = []

            def respond(url, *, timeout, seen=seen):
                parts = url.split("/")
                seen.append((parts[3], timeout))
                rows = [
                    {key.upper(): value for key, value in row.items()}
                    for row in raw_rows()
                    if row["stdr_yyqu_cd"] == "20241"
                ]
                for row in rows:
                    row["STDR_YYQU_CD"] = parts[-2]
                return io.BytesIO(
                    json.dumps(
                        {
                            "VwsmTrdarStorQq": {
                                "RESULT": {"CODE": "INFO-000"},
                                "list_total_count": len(rows),
                                "row": rows,
                            }
                        }
                    ).encode()
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
                    patch("app.agents.business_lifecycle.client.urlopen", side_effect=respond),
                    patch("app.llm.client.complete_json", side_effect=completion),
                ):
                    result = await registry["business_lifecycle"](task())
            self.assertEqual(result.status, "partial")
            self.assertEqual(seen, [("captured-key", 0.25)] * (4 if base_quarter else 5))

    async def test_parallel_registries_keep_per_agent_settings(self):
        from app.services.settings import ExecutionSettings

        seen = []

        def fake(agent_id):
            async def analyze(task, **kwargs):
                await asyncio.sleep(0)
                if agent_id == "commercial_area":
                    model = kwargs["settings"].llm_model
                elif agent_id == "floating_population":
                    model = kwargs["select"].keywords["settings"].model
                else:
                    model = kwargs["llm_settings"].model
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
                    {f"{name.upper()}_LLM_MODEL": f"{request}-{name}" for name in AGENT_IDS},
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
                (request, name, f"{request}-{name}")
                for request in ("first", "second")
                for name in AGENT_IDS
            },
        )

    def test_default_registry_uses_all_three_and_legacy_commercial_settings(self):
        from app.agents.commercial_area.config import Settings

        registry = default_agents(Settings(analysis_radius_m=200))
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
