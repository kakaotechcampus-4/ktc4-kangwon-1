"""전송 공통화 후 에이전트의 설정 주입과 계산 보존을 검증합니다."""

import asyncio
import importlib
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

from openai.types.chat import ChatCompletionMessage

from app.agents.commercial_area.config import Settings
from app.agents.commercial_area.llm import summarize
from app.agents.decision.llm import generate_decision
from app.agents.floating_population.llm import SelectionUnavailable, select_blocks
from app.agents.orchestration.llm import generate_action
from app.llm.config import LLMSettings


class CallerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.enterContext(
            patch(
                "httpx.AsyncHTTPTransport.handle_async_request",
                side_effect=AssertionError("외부 연결 금지"),
            )
        )
        self.settings = LLMSettings(
            model="injected", api_key="test", base_url="https://invalid.example/v1"
        )

    async def test_decision_injection_keeps_schema_validation_and_safe_fields(self):
        payload = {"SECRET-KEY": "private"}
        with patch("app.llm.client.complete_json", new=AsyncMock(return_value=payload)) as call:
            with self.assertRaises(RuntimeError) as raised:
                await generate_decision("지침", "{}", settings=self.settings)
        self.assertNotIn("SECRET-KEY", str(raised.exception))
        self.assertIs(call.call_args.args[2], self.settings)

    async def test_tool_injection_rejects_multiple_calls(self):
        message = ChatCompletionMessage.model_validate(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": str(i),
                        "type": "function",
                        "function": {"name": "prepare_address", "arguments": "{}"},
                    }
                    for i in range(2)
                ],
            }
        )
        with patch("app.llm.client.complete_tools", new=AsyncMock(return_value=message)) as call:
            with self.assertRaisesRegex(RuntimeError, "하나"):
                await generate_action([], [], settings=self.settings)
        self.assertIs(call.call_args.args[2], self.settings)

    async def test_selection_injection_keeps_domain_validation_and_missing_fallback(self):
        with patch(
            "app.llm.client.complete_json",
            new=AsyncMock(return_value={"include": ["trend"], "dropped_reason": "요약"}),
        ) as call:
            self.assertEqual(await select_blocks("{}", settings=self.settings), (["trend"], "요약"))
        self.assertIs(call.call_args.args[2], self.settings)
        with self.assertRaises(SelectionUnavailable):
            await select_blocks("{}")

    async def test_commercial_settings_priority_and_single_http_attempt_policy(self):
        with patch.dict(os.environ, {"ELICE_MODEL": "legacy", "COMMERCIAL_AREA_LLM_MODEL": "area"}):
            self.assertEqual(Settings.from_env().llm_model, "area")
            self.assertEqual(Settings.from_env(llm_model="explicit").llm_model, "explicit")
        settings = Settings(
            llm_model="injected", llm_api_key="test", llm_base_url="https://invalid.example/v1"
        )
        with patch(
            "app.llm.client.complete_json", new=AsyncMock(side_effect=RuntimeError("private"))
        ) as call:
            result, warning = await summarize({}, settings)
        self.assertIsNone(result)
        self.assertNotIn("private", warning)
        self.assertEqual(call.await_count, 1)
        with patch(
            "app.llm.client.complete_json", new=AsyncMock(side_effect=[{}, {"overall": "성공"}])
        ) as call:
            result, warning = await summarize({}, settings)
        self.assertEqual(result["overall"], "성공")
        self.assertIsNone(warning)
        self.assertEqual(call.await_count, 2)
        self.assertIsNone((await summarize({}, Settings()))[0])

    async def test_lifecycle_worker_bridge_preserves_calculated_score(self):
        lifecycle_llm = importlib.import_module("app.agents.business_lifecycle.llm")
        source = {
            "scope": {"period": {"quarter_count": 4}},
            "scoring_method": {},
            "industries": [
                {
                    "industry_id": "I201",
                    "industry_name": "한식",
                    "lifecycle_score": 55,
                    "confidence": "high",
                }
            ],
        }
        payload = {"industry_scores": [dict(source["industries"][0], lifecycle_score=999)]}
        with patch("app.llm.client.complete_json", new=AsyncMock(return_value=payload)) as call:
            result = await asyncio.to_thread(lifecycle_llm.run_llm_analysis, source, self.settings)
        self.assertEqual(result["industry_scores"][0]["lifecycle_score"], 55)
        self.assertIs(call.call_args.args[2], self.settings)
        self.assertEqual(json.loads(call.call_args.args[1])["industries"][0]["lifecycle_score"], 55)
        with self.assertRaisesRegex(RuntimeError, "이벤트 루프"):
            lifecycle_llm.run_llm_analysis(source, self.settings)

    async def test_mapping_examples_share_transport_and_keep_matching_policy(self):
        from examples import match_upjong, match_upjong_by_small

        settings = Settings(
            llm_model="test", llm_api_key="test", llm_base_url="https://invalid.example/v1"
        )
        rows = [{"SVC_INDUTY_CD": "CS100001", "SVC_INDUTY_CD_NM": "한식"}]
        with patch(
            "app.llm.client.complete_json",
            new=AsyncMock(
                return_value={"matches": [{"seoul_code": "CS100001", "candidates": ["I201"]}]}
            ),
        ):
            self.assertEqual(await match_upjong.ask(settings, [], rows), {"CS100001": ["I201"]})
        picks = {}
        with patch(
            "app.llm.client.complete_json",
            new=AsyncMock(
                return_value={"matches": [{"seoul_code": "CS100001", "small_codes": ["s1", "bad"]}]}
            ),
        ):
            await match_upjong_by_small.fill_with_model(
                settings, {"s1": ("한식", "I201")}, rows, picks, {}
            )
        self.assertEqual(picks, {"CS100001": (["s1"], "모델")})
