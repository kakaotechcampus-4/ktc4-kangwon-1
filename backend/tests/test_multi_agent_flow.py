"""외부 호출 없이 HTTP·그래프·SQLite 전체 경로를 검사합니다."""

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx
import openai
from fastapi.testclient import TestClient

from app.db import repository as repo
from app.evidence import scalar_records
from app.llm.config import LLMSettings
from app.main import create_app
from app.mocks import mock_agents, mock_generate, mock_resolve
from app.services.analysis import execute_analysis, retry_decision
from app.services.settings import ExecutionSettings


class MultiFlowTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.network = self.enterContext(
            patch("httpx.AsyncClient.send", side_effect=AssertionError("외부 호출 금지"))
        )
        self.client = self.enterContext(
            TestClient(
                create_app(
                    settings=ExecutionSettings(
                        db_path=Path(folder) / "flow.sqlite3", analysis_mode="multi_agent"
                    ),
                    load_env=False,
                )
            )
        )

    def test_map_consult_question_resume_and_history(self):
        started = self.client.post(
            "/api/v1/analyses?mock=true",
            json={
                "address": "시험 주소",
                "radius_m": 300,
                "with_map": True,
                "allow_questions": True,
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        waiting = started.json()
        path = "/api/v1/analyses/" + waiting["request_id"]
        saved = self.client.get(path).json()
        self.assertEqual(saved["status"], "waiting_for_input")
        self.assertEqual(saved["map_observation"]["radius_m"], 300)
        self.assertEqual(len(saved["deliberation"]["briefs"]), 3)
        self.assertEqual(saved["deliberation"]["answers"][0]["tool_calls"][0]["status"], "ok")
        self.assertNotIn("execution_json", saved)
        answer = {
            "request_id": waiting["request_id"],
            "question_set_id": waiting["question_set_id"],
            "answers": [],
        }
        final = self.client.post(path + "/answers?mock=true", json=answer)
        self.assertEqual(final.status_code, 200, final.text)
        self.assertIsNotNone(final.json()["map_observation"])
        self.assertEqual(
            final.json(), self.client.post(path + "/answers?mock=true", json=answer).json()
        )
        self.assertEqual(len(self.client.get(path).json()["analyses"]), 3)
        self.network.assert_not_called()

    def test_immediate_final_never_requires_questions(self):
        response = self.client.post("/api/v1/analyses?mock=true", json={"address": "시험 주소"})
        self.assertEqual(response.status_code, 200, response.text)
        saved = self.client.get("/api/v1/analyses/" + response.json()["request_id"]).json()
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["deliberation"]["consult_round"], 0)
        self.assertIsNone(saved["questions"])
        self.network.assert_not_called()


class MultiTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_transport_boundary_counts_correction_and_saved_retry(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        path = Path(folder) / "transport.sqlite3"
        llm = LLMSettings(api_key="test", model="test", base_url="https://example.invalid/v1")
        settings = ExecutionSettings(analysis_mode="multi_agent", db_path=path, decision_llm=llm)
        requests = []
        reject = True

        def respond(request):
            payload = json.loads(request.content)
            requests.append(payload)
            if payload.get("tools"):
                data = json.loads(payload["messages"][1]["content"])["analysis"]["data"]
                record = scalar_records(data)[0]
                message = {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "finish",
                            "type": "function",
                            "function": {
                                "name": "finish",
                                "arguments": json.dumps(
                                    {
                                        "headline": "확인",
                                        "findings": [
                                            {
                                                "claim": "원자료 확인",
                                                "signal": "context",
                                                "industry_code": record["industry_code"],
                                                "evidence": [{"path": record["path"]}],
                                            }
                                        ],
                                        "limitations": [],
                                    }
                                ),
                            },
                        }
                    ],
                }
                finish = "tool_calls"
            else:
                result = mock_generate("", "")
                if reject:
                    result["recommendations"][0]["evidence"][0]["path"] = "/missing"
                message, finish = {"role": "assistant", "content": json.dumps(result)}, "stop"
            return httpx.Response(
                200,
                json={
                    "id": "test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "test",
                    "choices": [{"index": 0, "finish_reason": finish, "message": message}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                },
            )

        sdk_class = openai.AsyncOpenAI

        def sdk(**kwargs):
            self.assertEqual(kwargs["max_retries"], 0)
            return sdk_class(
                **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
            )

        with patch("app.llm.client.openai.AsyncOpenAI", side_effect=sdk):
            with self.assertRaises(ValueError):
                await execute_analysis(
                    "주소",
                    request_id="r",
                    settings=settings,
                    resolve=mock_resolve,
                    agents=mock_agents(),
                )
            row = repo.get_request("r", db_path=path)
            self.assertEqual(row["status"], "failed")
            self.assertEqual(json.loads(row["execution_json"])["budget"]["used"], 5)
            reject = False
            result = await retry_decision(
                "r",
                failed_at=row["completed_at"],
                settings=replace(settings, analysis_mode="single_decision"),
            )
        self.assertEqual(result.request_id, "r")
        state = repo.get_deliberation("r", db_path=path)
        self.assertEqual(state["execution"]["budget"]["used"], 6)
        self.assertEqual(
            [c["input_tokens"] for c in state["execution"]["budget"]["calls"]], [10] * 6
        )
        self.assertEqual(len(requests), 6)
        self.assertEqual(len(repo.list_agent_results("r", db_path=path)), 3)
